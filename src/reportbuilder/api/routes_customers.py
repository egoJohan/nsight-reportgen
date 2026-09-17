"""Asiakas and Case routes — nSight's OWN API, served to nSight's web app.

Nothing here reaches datahive directly: these call the Repository, which calls
the four-method seam, which speaks only generic `/api/v1/objects`. Datahive
never learns what an asiakas is (floor rule 6).

Trello: Asiakkuuden hallinta. Speksi 2 P-O-01. Additive — the existing
`/cases/*` surface is untouched while the UI moves over.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from reportbuilder.api.deps_auth import (
    current_user, require_case, require_case_in_customer,
    require_case_in_customer_write, require_case_write, require_customer,
    require_customer_write, require_material,
)
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import session
from reportbuilder.auth.permissions import EDIT, Grant, User, may_write
from reportbuilder.store.repository import ReportRef, Repository
from reportbuilder.store.repository_client import deliverables_only
from reportbuilder.store.seam import AuthContext, NotFound

customers_router = APIRouter()


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class CustomerAccessBody(BaseModel):
    """One person's access to ONE customer.

    `mode` null removes it. Scoped deliberately: this never carries a list of
    grants, so a caller who administers one customer cannot reach across to
    another by sending an extra row — which `PUT /users/{id}/grants` would
    allow, and is why that one is admin-only. (Johan, 2026-09-14)
    """
    user_id: str = Field(min_length=1)
    mode: str | None = Field(default=None, pattern="^(view|edit)$")


class PermissionModeBody(BaseModel):
    """How a customer decides who may reach it.

    "inherit" respects the Domains setting, as every customer always has.
    "manual" takes nothing from it: only the people named on the customer
    itself get in. (Johan, 2026-09-14)
    """
    mode: str = Field(pattern="^(inherit|manual)$")


def _name(body: NameBody) -> str:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name cannot be empty")
    return name


def _managing(repo: Repository, auth: AuthContext, customer_id: str, user: User):
    """The customer, if *user* may administer who reaches it — else 404/403.

    THE OWNER decides. Being an admin is the right to manage users, not a key
    to a customer's data (spec §5): if it opened this, any admin could name
    themselves on any customer, which is what the manual mode exists to stop.

    A customer recorded before ownership existed has nobody to ask, and
    refusing everybody would leave it unmanageable for ever with no way back
    through the UI. Those fall back to an admin — narrow, and closed as soon as
    such a customer is given an owner. (Johan, 2026-09-14)
    """
    customer = repo.find_customer(auth, customer_id)
    if customer is None:
        raise HTTPException(404, f"Customer '{customer_id}' not found")
    allowed = (user.id == customer.owner_id) if customer.owner_id else bool(user.is_admin)
    if not allowed:
        raise HTTPException(
            403, "Only this customer's owner can manage its permissions")
    return customer


def _report_stats(reports: list[ReportRef]) -> tuple[int, int]:
    """(completed, draft) counts for the "N drafts, N completed" statistic
    under a study on the customer page, and its aggregate on the customer
    list.

    Matches the report row badge (ReportsSection.tsx) so the two pages never
    disagree: "Generated" there means `rendered` is true (a deck exists) --
    that is "completed" here. "Draft" and "Empty" (no charts, no deck) both
    fold into "draft": neither is a deliverable someone can walk away with.

    Folding Empty into Draft is also what keeps this cheap. Telling Draft
    and Empty apart needs a chart count, which lives in the report BODY, not
    the sidecar `ReportRef` is read from (list_reports /
    list_reports_for_customer read sidecars only, on purpose -- see their
    docstrings). Splitting them here would mean fetching every report body
    for every study, just for a number nobody asked to see chart counts in.
    `rendered` is already on the sidecar, so this needs no extra reads
    beyond the ones the caller already made to build `reports`.
    """
    completed = sum(1 for r in reports if r.rendered)
    return completed, len(reports) - completed


@customers_router.post("/customers", status_code=201)
def create_customer(body: NameBody, auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository),
                    user: User = Depends(current_user)) -> dict:
    # The creator is the owner, recorded here and never recomputed.
    c = repo.create_customer(auth, _name(body), owner_id=user.id)
    # ...and the creator can work in what they just made. Without this the
    # customer exists but is invisible to the person who created it: grants
    # are the only thing that admits anyone to a customer (admin is the right
    # to manage users, not a key to their data), and a brand-new customer has
    # none. The redirect landed on a page that answered 404.
    #
    # Grants are re-read from the store rather than taken from `user`, whose
    # own copy can be up to CACHE_TTL_SECONDS old — writing that back would
    # quietly undo a grant made in the meantime.
    stored = repo.get_user(auth, user.id)
    if stored is not None:
        repo.set_grants(auth, stored.id, tuple(stored.grants) + (Grant(c.id, EDIT),))
        # The next request must see it. Waiting out the cache would leave the
        # creator staring at their own new customer's 404 for half a minute.
        session.forget_user(stored.id)
    return {"id": c.id, "name": c.name}


@customers_router.get("/customers")
def list_customers(auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository),
                   user: User = Depends(current_user)) -> list[dict]:
    """Only the customers this caller may see — datahive filters the listing,
    so an over-permissive UI cannot widen it.

    `can_edit` rides along per row (see resolve_case's docstring for the
    general rationale) because the sidebar shows a per-customer "New study"
    link right here in the listing — creating a study is a write against the
    CUSTOMER, so the answer has to be per-row, not a single flag for the page.

    Study count and the owner ride along too, for the same reason: the
    customer page shows both under each name, and a second round trip per
    customer for each would just move the cost from here to there. Report
    counts do NOT — this page shows the number of studies, and the reports
    under one of them are the studies list's business (that route computes
    its own, per study). Dropping them from here also drops a get() per
    report from every load of this page.

    ONE owner, the user who created the customer (`Customer.owner_id`), not
    everyone holding `edit`. Those are different questions: "who owns this"
    is settled once at creation, while "who may write here" changes every
    time access is granted — keying the first off the second turned every
    colleague given access into another owner. Deciding who may APPROVE an
    access request is still the second question, and stays where it is
    (`access_request_mail.decision_makers`): a person who can write to a
    customer can act on it, whether or not they created it.

    `list_users` is fetched ONCE, outside the loop, and reused for every
    row — an id lookup in the same in-memory list instead of a users
    listing per customer. Only a display NAME rides along, falling back to
    email only when a user has never set one, and nothing else about them
    (no email otherwise, no is_admin, no grants) — `GET /users` is
    admin-only precisely because a user listing is not public, and this is
    a deliberately narrow crack in that: any signed-in user who can already
    see a customer (this route is grant-filtered, see above) can now also
    see who owns it, nothing more. A customer created before ownership was
    recorded has no owner, and says so by omission rather than by guessing
    at one.

    Cost note: ONE listing of every case, counted per customer
    (`count_cases_by_customer`) — the same number of hive calls however many
    customers there are. `list_users` adds one listing + 2 gets per tenant user,
    paid once for the page, not once per customer.
    """
    customers = repo.list_customers(auth, user=user)
    # Names only — this page prints who owns a customer and nothing else about
    # them, and `list_users` reads a second object per user for grants it would
    # throw away. (Johan, 2026-09-16)
    names = repo.list_user_names(auth)
    # One read for the whole page, not one per row.
    modes = repo.customer_modes(auth)
    # Every customer's study count from one listing, not one listing each.
    case_counts = repo.count_cases_by_customer(auth, user=user)
    out = []
    for c in customers:
        owner_name = names.get(c.owner_id)
        out.append({
            "id": c.id, "name": c.name, "template_id": c.template_id,
            "can_edit": may_write(user, c.id),
            # Counted from the listing; the studies themselves are not read.
            "case_count": case_counts.get(c.id, 0),
            "permission_mode": modes.get(c.id, "inherit"),
            "owner": ({"id": c.owner_id, "name": owner_name}
                      if owner_name is not None else None),
        })
    return out


# `GET /customers/names` is GONE (Johan, 2026-09-09). It returned every customer
# id and name in the tenant to any signed-in user, so the sidebar could list the
# ones a caller holds no grant on behind a padlock and offer to request access.
# Those rows are no longer drawn — a customer you cannot open is not shown —
# which removes the reason for the roster, and the roster was the widest thing
# this product told a signed-in stranger: for a research agency the client list
# is itself the commercially sensitive part.
#
# `GET /customers/{id}/name` below STAYS. That one answers about a single id the
# caller already has, which is what the request-access page needs when somebody
# is sent a link to a customer they cannot yet open. One name on request is a
# different disclosure from the whole roster unasked.


@customers_router.get("/customers/{customer_id}")
def get_customer(customer_id: str, auth: AuthContext = Depends(get_auth),
                 repo: Repository = Depends(get_repository),
                 user: User = Depends(require_customer)) -> dict:
    try:
        c = repo.get_customer(auth, customer_id)
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"id": c.id, "name": c.name, "template_id": c.template_id,
            "can_edit": may_write(user, c.id),
            "permission_mode": repo.customer_modes(auth).get(c.id, "inherit")}


@customers_router.get("/customers/{customer_id}/name")
def customer_name(customer_id: str, auth: AuthContext = Depends(get_auth),
                  repo: Repository = Depends(get_repository),
                  user: User = Depends(current_user)) -> dict:
    """The one thing an ungranted signed-in user may learn about a customer
    they cannot open: that it exists, and what it is called.

    Deliberately breaks the 404-for-absence rule (spec §5, `deps_auth._check`)
    that every other route in this file keeps: an ungranted customer is
    normally ABSENT, not forbidden, so the API never confirms a path it will
    not open. But the no-access page (the point of this whole task) has to
    say "you don't have access to Attendo" — and that sentence necessarily
    reveals Attendo exists. The controller weighed that one-line leak
    against a no-access page that cannot even name what it is refusing, and
    accepted it, NARROWLY: id and name, nothing else — no cases, no counts,
    no template, no members. `require_customer` is what implements the 404
    rule this route exists to carve one exception out of, so it is guarded
    by `current_user` alone (any signed-in user) instead. A user who is not
    signed in still gets 401 from `current_user` and learns nothing.

    Do not widen this response, and do not copy this "any signed-in user"
    pattern onto another route without going back to the controller — this
    is the one deliberate crack in an otherwise-absolute rule, not a
    precedent.
    """
    try:
        c = repo.get_customer(auth, customer_id)
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"id": c.id, "name": c.name}


@customers_router.patch("/customers/{customer_id}")
def rename_customer(customer_id: str, body: NameBody,
                    auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository),
                    user: User = Depends(require_customer_write)) -> dict:
    try:
        c = repo.rename_customer(auth, customer_id, _name(body))
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"id": c.id, "name": c.name}


@customers_router.get("/customers/{customer_id}/access")
def get_customer_access(customer_id: str, auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository),
                        user: User = Depends(current_user)) -> dict:
    """Who reaches this customer, and who could be added.

    Exists so the permissions dialog works for an OWNER who is not an admin.
    It used to read `GET /users`, which is admin-only and tenant-wide, so an
    owner opening the dialog got 403 and an empty list — able to close their
    customer off but not to say who stays.

    The roster it discloses is the same one an admin already sees, narrowed to
    what a picker needs (id, name, email) and served only to someone who
    administers THIS customer. That is deliberately not `GET /customers/names`,
    which was removed for handing the whole client list to any signed-in
    stranger: here the caller already owns the customer they are asking about.
    """
    customer = _managing(repo, auth, customer_id, user)
    people, candidates = [], []
    for u in repo.list_users(auth):
        grant = next((g for g in u.grants if g.scope == customer_id), None)
        row = {"id": u.id, "email": u.email, "name": u.name,
               "is_owner": bool(customer.owner_id) and u.id == customer.owner_id}
        if grant is None:
            candidates.append(row)
        else:
            people.append({**row, "mode": grant.mode})
    return {"id": customer_id,
            "permission_mode": repo.customer_modes(auth).get(customer_id, "inherit"),
            "owner_id": customer.owner_id or None,
            "people": people, "candidates": candidates}


@customers_router.put("/customers/{customer_id}/access")
def set_customer_access(customer_id: str, body: CustomerAccessBody,
                        auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository),
                        user: User = Depends(current_user)) -> dict:
    """Give one person view/edit on this customer, or take it away.

    Only this customer's entry in that person's grants is touched; every other
    customer they hold is carried through untouched. That is the whole reason
    this exists beside `PUT /users/{id}/grants`: the admin route replaces the
    WHOLE list, so handing it to an owner would hand them every customer.

    The owner's own edit grant cannot be removed or downgraded here. They keep
    the customer they own — the same guarantee `set_permission_mode` enforces
    when it switches to manual, made in both places so neither can undo it.
    """
    customer = _managing(repo, auth, customer_id, user)
    target = repo.get_user(auth, body.user_id)
    if target is None:
        raise HTTPException(404, f"User '{body.user_id}' not found")

    if customer.owner_id and body.user_id == customer.owner_id and body.mode != EDIT:
        raise HTTPException(
            409, "The owner always keeps edit access to their own customer")

    rest = tuple(g for g in target.grants if g.scope != customer_id)
    repo.set_grants(auth, target.id,
                    rest + ((Grant(customer_id, body.mode),) if body.mode else ()))
    # At once, not within the cache TTL -- taking access away is the direction
    # that matters, the same reasoning as `PUT /users/{id}/grants`.
    session.forget_user(target.id)
    return {"id": customer_id, "user_id": target.id, "mode": body.mode}


@customers_router.put("/customers/{customer_id}/permission-mode")
def set_permission_mode(customer_id: str, body: PermissionModeBody,
                        auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository),
                        user: User = Depends(current_user)) -> dict:
    """Switch a customer between inheriting the domain policy and managing its
    own access.

    THE OWNER decides, not any admin. Being an admin is the right to manage
    users, not a key to a customer's data (spec §5) — and if it opened this
    control too, any admin could switch a customer to manual and name
    themselves, which is the one thing the setting exists to prevent.

    A customer created before ownership was recorded has no owner to ask, and
    refusing everybody would leave it permanently unmanageable with no way back
    through the UI. Those fall back to an admin, deliberately and narrowly: it
    is the legacy path, and it closes as soon as such a customer is given an
    owner. (Johan, 2026-09-14)

    Turning a customer MANUAL withdraws the domain's grant from it, so whoever
    reached it only through their domain loses it — including, on an ownerless
    customer, the person making the change. Taffel is exactly that: no owner,
    and an admin whose access came from `egoiq.com`, who switched it and locked
    themselves out. So this ensures an explicit edit grant for the owner, or
    for the caller when there is none, before the switch takes effect. A
    customer must never become unreachable by everybody.
    """
    customer = _managing(repo, auth, customer_id, user)

    if body.mode == "manual":
        # Whoever must still be able to reach it afterwards: the owner when
        # there is one, otherwise the admin making the decision.
        keeper_id = customer.owner_id or user.id
        keeper = repo.get_user(auth, keeper_id)
        if keeper is not None and not any(g.scope == customer_id and g.mode == EDIT
                                          for g in keeper.grants):
            repo.set_grants(auth, keeper.id,
                            tuple(keeper.grants) + (Grant(customer_id, EDIT),))

    repo.set_customer_mode(auth, customer_id, body.mode)
    # Every cached identity now describes a policy that no longer holds, and
    # there is no list of who this touches -- the same reasoning as
    # `PUT /settings/access`. Without it an admin closes a customer off, is
    # told it is done, and the people it withdrew carry on reading it for
    # another half minute.
    session.forget_all()
    return {"id": customer_id, "permission_mode": body.mode}


@customers_router.post("/customers/{customer_id}/cases", status_code=201)
def create_case(customer_id: str, body: NameBody,
                auth: AuthContext = Depends(get_auth),
                repo: Repository = Depends(get_repository),
                user: User = Depends(require_customer_write)) -> dict:
    try:
        k = repo.create_case(auth, customer_id, _name(body))
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"id": k.id, "customer_id": k.customer_id, "name": k.name,
            "template_id": k.template_id}


@customers_router.get("/customers/{customer_id}/cases")
def list_cases(customer_id: str, auth: AuthContext = Depends(get_auth),
               repo: Repository = Depends(get_repository),
               user: User = Depends(require_customer)) -> list[dict]:
    """`completed_reports`/`draft_reports` ride along per study — see
    `_report_stats` for the definition (matches the report row badge) and
    why Empty folds into draft.

    One `list_reports_for_customer` call covers every study's reports (see
    its docstring) — this does NOT loop `list_reports` per case, which
    would turn one page view into one listing call per study.
    """
    cases = repo.list_cases(auth, customer_id, user=user)
    reports_by_case: dict[str, list[ReportRef]] = {}
    # The same rule the report list applies, or the card promises reports the
    # caller then cannot open — "3 drafts", clicked, empty.
    for r in deliverables_only(user, repo.list_reports_for_customer(
            auth, customer_id, user=user)):
        reports_by_case.setdefault(r.case_id, []).append(r)
    out = []
    for k in cases:
        completed, draft = _report_stats(reports_by_case.get(k.id, []))
        out.append({"id": k.id, "customer_id": k.customer_id, "name": k.name,
                    "template_id": k.template_id,
                    "completed_reports": completed, "draft_reports": draft})
    return out


@customers_router.get("/customers/{customer_id}/cases/{case_id}")
def get_case(customer_id: str, case_id: str, auth: AuthContext = Depends(get_auth),
             repo: Repository = Depends(get_repository),
             user: User = Depends(require_case_in_customer)) -> dict:
    try:
        k = repo.get_case(auth, customer_id, case_id)
    except NotFound:
        raise HTTPException(404, f"Case '{case_id}' not found") from None
    return {"id": k.id, "customer_id": k.customer_id, "name": k.name,
            "template_id": k.template_id}


@customers_router.patch("/customers/{customer_id}/cases/{case_id}")
def rename_case(customer_id: str, case_id: str, body: NameBody,
                auth: AuthContext = Depends(get_auth),
                repo: Repository = Depends(get_repository),
                user: User = Depends(require_case_in_customer_write)) -> dict:
    try:
        k = repo.rename_case(auth, customer_id, case_id, _name(body))
    except NotFound:
        raise HTTPException(404, f"Case '{case_id}' not found") from None
    return {"id": k.id, "customer_id": k.customer_id, "name": k.name,
            "template_id": k.template_id}


@customers_router.get("/reports/recent")
def recent_reports(limit: int = Query(default=10, ge=1, le=50),
                   auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository),
                   user: User = Depends(current_user)) -> list[dict]:
    """The caller's most recently modified reports, newest first.

    "Accessible to this person" is the store's answer for what may be READ; what
    a view-only caller is SHOWN is narrower, and is `deliverables_only` — the
    landing page listed work in progress that vanished when they clicked it.
    """
    return [
        {"id": r.id, "case_id": r.case_id, "customer_id": r.customer_id,
         "name": r.name, "modified_at": r.modified_at}
        for r in deliverables_only(user, repo.recent_reports(auth, limit=limit,
                                                             user=user))
    ]


@customers_router.get("/cases/{case_id}/resolve")
def resolve_case(case_id: str, auth: AuthContext = Depends(get_auth),
                 repo: Repository = Depends(get_repository),
                 user: User = Depends(require_case)) -> dict:
    """Resolve a bare case id to its case and owning customer.

    The UI holds case ids in URLs that predate the hierarchy, so it needs a way
    to ask "which customer does this belong to, and what is it called?" without
    already knowing the answer.

    Also answers the LOCAL capability question — "may THIS user edit THIS
    case" — as `can_edit`, computed straight from `may_write`. This is a UI
    courtesy, not a security control: every write route re-checks the same
    grant independently (require_case_write), so a viewer who forges a request
    around a hidden button still gets 403. `/auth/me` deliberately carries no
    grants (see test_me_shape_carries_no_grants_or_password_fields) because
    "what may they do here" is a per-object question, not a global one — this
    is where it gets answered, for the one object this page is about.
    """
    k = repo.find_case(auth, case_id)
    if k is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    customer_name = ""
    try:
        customer_name = repo.get_customer(auth, k.customer_id).name
    except NotFound:
        pass
    return {"id": k.id, "name": k.name, "customer_id": k.customer_id,
            "customer_name": customer_name, "template_id": k.template_id,
            "can_edit": may_write(user, f"{k.customer_id}/{k.id}")}


def _case_name_from_filename(filename: str) -> str:
    """A study is named after the file imported into it.

    Strips the extension only — the rest of the name is the analyst's, and
    second-guessing it produces worse titles than leaving it alone.
    """
    stem = (filename or "").rsplit("/", 1)[-1]
    if "." in stem:
        stem = stem.rsplit(".", 1)[0]
    return stem.strip() or "New study"


@customers_router.post("/customers/{customer_id}/cases/from-material", status_code=201)
async def create_case_from_material(
    customer_id: str,
    file: UploadFile = File(...),
    auth: AuthContext = Depends(get_auth),
    repo: Repository = Depends(get_repository),
    user: User = Depends(require_customer_write),
) -> dict:
    """Create a tutkimus from an uploaded .sav, in one step.

    A tutkimus corresponds to a material, so creating one without data leaves an
    empty shell the user then has to fill. Uploading IS the creation.
    """
    data = await file.read()
    if not data:
        raise HTTPException(422, "Empty file")
    try:
        k = repo.create_case(auth, customer_id, _case_name_from_filename(file.filename))
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    m = repo.attach_material(auth, customer_id, k.id, file.filename or k.name, data)
    return {"id": k.id, "customer_id": customer_id, "name": k.name,
            "material_id": m.id, "material_name": m.name, "size": m.size}


@customers_router.get("/customers/{customer_id}/cases/{case_id}/materials")
def list_case_materials(customer_id: str, case_id: str,
                        auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository),
                        user: User = Depends(require_case_in_customer)) -> list[dict]:
    return [{"id": m.id, "name": m.name, "size": m.size}
            for m in repo.list_materials(auth, customer_id, case_id, user=user)]


@customers_router.get("/materials/{material_id}/locate")
def locate_material(material_id: str, auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository),
                    user: User = Depends(require_material)) -> dict:
    """Resolve a bare material id to its case and customer.

    The question, preview and render routes are all keyed by material id from
    before the hierarchy existed; this lets them keep working while the storage
    moves underneath them.
    """
    m = repo.find_material(auth, material_id)
    if m is None:
        raise HTTPException(404, f"Material '{material_id}' not found")
    return {"id": m.id, "name": m.name, "size": m.size,
            "case_id": m.case_id, "customer_id": m.customer_id}
