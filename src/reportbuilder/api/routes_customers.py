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
    current_user, require_case, require_case_write, require_customer,
    require_customer_write, require_material,
)
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import EDIT, User, may_write
from reportbuilder.store.repository import Repository, ReportRef
from reportbuilder.store.seam import AuthContext, NotFound

customers_router = APIRouter()


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _name(body: NameBody) -> str:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name cannot be empty")
    return name


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
    c = repo.create_customer(auth, _name(body))
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

    Study count, report stats and owners ride along too, for the same
    reason: the customer page shows all three under each name, and a
    second round trip per customer for each would just move the cost from
    here to there.

    `list_users` is fetched ONCE, outside the loop, and reused for every
    row's owners — filtering the same in-memory list per customer instead
    of a users listing per customer. `EDIT` on the customer's own scope is
    this app's only notion of "owns a customer" (see
    `access_request_mail.decision_makers`, the access-request approval
    flow, which already keys "owner" the exact same way — this does not
    invent a second definition). Only a display NAME rides along per owner,
    falling back to email only when a user has never set one, and nothing
    else about them (no email otherwise, no is_admin, no other grants) —
    `GET /users` is admin-only precisely because a user listing is not
    public, and this is a deliberately narrow crack in that: any signed-in
    user who can already see a customer (this route is grant-filtered, see
    above) can now also see who owns it, nothing more.

    Cost note: for each customer this is one `list_cases` and one
    `list_reports_for_customer` — both single listing calls regardless of
    study count (see that method's docstring) — plus one get() per report
    sidecar. So the shape is O(customers) listings + O(reports) gets across
    the whole page, not O(customers × studies). `list_users` adds one
    listing + 2 gets per tenant user, paid once for the page, not once per
    customer. Fine at today's scale (a handful of customers, tens of
    reports); if either count reaches the thousands the fix is a
    denormalised counter kept on write, not a bigger fetch here — the same
    trade `recent_reports` already documents for its own listing.
    """
    customers = repo.list_customers(auth, user=user)
    users = repo.list_users(auth)
    out = []
    for c in customers:
        cases = repo.list_cases(auth, c.id, user=user)
        completed, draft = _report_stats(
            repo.list_reports_for_customer(auth, c.id, user=user))
        owners = [u for u in users
                 if any(g.scope == c.id and g.mode == EDIT for g in u.grants)]
        out.append({
            "id": c.id, "name": c.name, "template_id": c.template_id,
            "can_edit": may_write(user, c.id),
            "case_count": len(cases),
            "completed_reports": completed,
            "draft_reports": draft,
            "owners": [{"id": o.id, "name": o.name or o.email} for o in owners],
        })
    return out


@customers_router.get("/customers/names")
def list_customer_names(auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository),
                        user: User = Depends(current_user)) -> list[dict]:
    """Id and name for EVERY customer in the tenant, to any signed-in user —
    the list form of `customer_name` below, and the same deliberate crack in
    the 404/absence rule (see that route's docstring for the full
    reasoning).

    This one reveals more at once: every signed-in user learns the full
    roster of customer NAMES, not just the one they happen to land on. That
    is a known, deliberate widening, not an oversight — the sidebar has to
    list every customer, including ones this caller holds no grant on, or
    there is nothing to click into and request access to; without this, the
    request-access flow (this whole task) has no target to name. Still id
    and name ONLY, same as `customer_name` — no cases, no reports, no
    counts, no template. Do not add a field here without going back to the
    controller.

    Kept OUT of `GET /customers` (`list_customers` above) deliberately: that
    route stays grant-filtered exactly as it is — spec §5.3,
    `test_the_other_customer_is_absent_from_listings` and the rest of
    test_permission_matrix.py assert on it, and folding an unfiltered
    listing into it would break that contract. Also distinct from the
    admin-only `GET /users/customers` (routes_users.py's
    `list_grantable_customers`): that one feeds an admin's grant picker and
    stays behind `require_admin` on purpose; THIS one is reachable by any
    signed-in user, on purpose, and weakening that other route's gate to
    reach for this use would be the wrong fix.

    Registered here, ahead of `get_customer`'s `/customers/{customer_id}`,
    on purpose: a literal path and a param path of the same segment count
    race by registration order in FastAPI/Starlette, and this one must win
    or a request for "/customers/names" would be swallowed as
    customer_id="names" instead. Do not move this below `get_customer`.
    """
    return [{"id": c.id, "name": c.name} for c in repo.list_customers(auth)]


@customers_router.get("/customers/{customer_id}")
def get_customer(customer_id: str, auth: AuthContext = Depends(get_auth),
                 repo: Repository = Depends(get_repository),
                 user: User = Depends(require_customer)) -> dict:
    try:
        c = repo.get_customer(auth, customer_id)
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"id": c.id, "name": c.name, "template_id": c.template_id,
            "can_edit": may_write(user, c.id)}


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
    for r in repo.list_reports_for_customer(auth, customer_id, user=user):
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
             user: User = Depends(require_case)) -> dict:
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
                user: User = Depends(require_case_write)) -> dict:
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

    "Accessible to this person" is the store's answer, not a filter applied
    here: the underlying listing only returns paths this caller may read.
    """
    return [
        {"id": r.id, "case_id": r.case_id, "customer_id": r.customer_id,
         "name": r.name, "modified_at": r.modified_at}
        for r in repo.recent_reports(auth, limit=limit, user=user)
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
                        user: User = Depends(require_case)) -> list[dict]:
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
