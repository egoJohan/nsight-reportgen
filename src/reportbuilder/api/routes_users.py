# src/reportbuilder/api/routes_users.py
"""The Users and Invitations HTTP surface: everything an admin does from
the Settings > Users screen (spec §5, §6). Every route here is
require_admin -- administering access is not itself a data grant (spec
§5), so nobody without the admin flag reaches this file at all.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException, Request

import logging

from reportbuilder.api.deps_auth import require_admin
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.api.routes_auth import public_origin
from reportbuilder.auth import invites, session, users
from reportbuilder.auth.permissions import Grant, User
from reportbuilder.store.repository import Invite, Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired

users_router = APIRouter(tags=["users"])


def _parse_grants(raw) -> tuple[Grant, ...]:
    """The grants in a request body, validated.

    Refuses the same scope twice with different modes. `_best` now resolves
    such a pair deterministically rather than by list order, so this is no
    longer a correctness problem — but a body naming one scope as both view
    and edit says the caller does not know what it is asking for, and guessing
    for them (either way) hides the mistake behind a permission decision
    nobody will look at again.
    """
    if not isinstance(raw, list):
        raise HTTPException(422, "grants must be a list")
    try:
        grants = tuple(
            Grant(g["scope"], g.get("mode", "view")) for g in raw if g.get("scope")
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(422, str(exc)) from exc
    modes: dict[str, str] = {}
    for g in grants:
        if modes.setdefault(g.scope, g.mode) != g.mode:
            raise HTTPException(
                422,
                f"scope {g.scope!r} is listed twice with different modes "
                f"({modes[g.scope]!r} and {g.mode!r}) — send it once",
            )
    # An exact duplicate is harmless, but storing it twice makes the grants
    # screen show one grant as two rows.
    return tuple({(g.scope, g.mode): g for g in grants}.values())


def _grant_out(repo: Repository, auth: AuthContext, g: Grant) -> dict:
    """A grant plus the name it stands for, so the Users screen can show
    "Attendo" rather than a bare id. Spec §5: a grant naming a customer or
    case that no longer exists is IGNORED for access -- here it is still
    SHOWN, with no name, so an admin can find and remove it."""
    parts = [s for s in g.scope.split("/") if s]
    customer = repo.find_customer(auth, parts[0]) if parts else None
    out = {"scope": g.scope, "mode": g.mode,
          "customer_name": customer.name if customer else None, "case_name": None}
    if customer is not None and len(parts) > 1:
        case = repo.find_case(auth, parts[1])
        out["case_name"] = case.name if case is not None else None
    return out


def _user_row(repo: Repository, auth: AuthContext, u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "is_admin": u.is_admin,
           "grants": [_grant_out(repo, auth, g) for g in u.grants]}


@users_router.get("/users")
def list_users(auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
              admin: User = Depends(require_admin)) -> list[dict]:
    return [_user_row(repo, auth, u) for u in repo.list_users(auth)]


@users_router.get("/users/customers")
def list_grantable_customers(auth: AuthContext = Depends(get_auth),
                             repo: Repository = Depends(get_repository),
                             admin: User = Depends(require_admin)) -> list[dict]:
    """Every customer in the tenant, id and name only -- so the grant editor
    on THIS screen has something to put in its picker.

    Why this exists: `GET /customers` (routes_customers.py) is grant-filtered
    (spec §5.3) -- an admin with no grants gets `[]` from it, by design (see
    `test_an_admin_without_grants_sees_nothing`). But that is exactly the
    state every BOOTSTRAP admin starts in, and a grant picker fed from that
    route is then empty: nobody can be granted anything, including the admin
    themselves, because there is no customer to name in the grant. That is a
    chicken-and-egg, not a bug in the filter -- the filter is right.
    "Administering access" and "having access" are deliberately different
    things (spec §5); this route answers the administration question ("what
    customers exist, so I can write a grant naming one") and nothing else.
    It carries no template, case, material, report or preview data -- only
    what a <select> needs -- and it is `require_admin`, not a general
    listing: a non-admin still has no way to enumerate customers they were
    not granted.

    Do not delete this as redundant with `/customers` -- for an admin with
    no grants they are NOT redundant, that is the whole reason this exists.
    Do not widen it into `/customers?all=true` or similar either: a route
    that sometimes ignores the grant filter is a much larger thing to audit
    than a route that only ever returns ids and names.
    """
    return [{"id": c.id, "name": c.name} for c in repo.list_customers(auth)]


@users_router.put("/users/{user_id}/grants")
def put_user_grants(user_id: str, body: dict = Body(...),
                    auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
                    admin: User = Depends(require_admin)) -> dict:
    if repo.get_user(auth, user_id) is None:
        raise HTTPException(404, f"User '{user_id}' not found")
    grants = _parse_grants(body.get("grants") or [])
    repo.set_grants(auth, user_id, grants)
    # At once, not within the cache TTL. Identity is cached per session, so a
    # grant TAKEN AWAY kept working for up to CACHE_TTL_SECONDS on every node
    # that had it cached: an admin removes somebody's access, is told it is
    # done, and that person carries on reading the customer for another half
    # minute. Adding a grant was already invalidated here — for convenience.
    # Removing one is the direction that matters.
    session.forget_user(user_id)
    return _user_row(repo, auth, repo.get_user(auth, user_id))


@users_router.patch("/users/{user_id}")
def patch_user(user_id: str, body: dict = Body(...),
              auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
              admin: User = Depends(require_admin)) -> dict:
    """Today this only ever changes `is_admin` -- the promote/demote
    control. Anything else in the body is refused rather than silently
    ignored, so a frontend typo fails loudly instead of doing nothing."""
    if "is_admin" not in body:
        raise HTTPException(422, "is_admin is the only field this route changes")
    if repo.get_user(auth, user_id) is None:
        raise HTTPException(404, f"User '{user_id}' not found")
    result = users.set_admin(repo, auth, user_id, bool(body["is_admin"]))
    if isinstance(result, users.LastAdminRefused):
        raise HTTPException(409, result.reason)
    # A demotion has to bite immediately — see put_user_grants. Admin is the
    # grant that opens every route there is.
    session.forget_user(user_id)
    return _user_row(repo, auth, result)


@users_router.delete("/users/{user_id}", status_code=204)
def remove_user_route(user_id: str, auth: AuthContext = Depends(get_auth),
                      repo: Repository = Depends(get_repository),
                      admin: User = Depends(require_admin)) -> None:
    if repo.get_user(auth, user_id) is None:
        raise HTTPException(404, f"User '{user_id}' not found")
    try:
        result = users.remove_user(repo, auth, user_id)
    except ConsentRequired as exc:
        # datahive gates destructive operations -- surfaced with its
        # approval envelope, same shape as delete_font (routes_settings.py).
        raise HTTPException(409, {
            "error": "consent_required",
            "message": "Removing this user needs approval in datahive.",
            "request_id": exc.request_id, "target": exc.target,
            "approve": exc.envelope.get("approval_urls", {}),
        }) from exc
    if isinstance(result, users.LastAdminRefused):
        raise HTTPException(409, result.reason)
    # Their sessions are gone with them; drop the cached identity too, or a
    # deleted user's request is still answered from memory. Their editing locks
    # go as well — nobody is coming back for them, and leaving them would bar
    # those reports until they expired.
    session.forget_user(user_id)
    try:
        repo.release_user_locks(auth, user_id)
    except Exception:  # noqa: BLE001 — the user is gone either way
        logging.getLogger(__name__).warning(
            "could not release the locks of a removed user", exc_info=True)


def _invite_out(i: Invite) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    if i.accepted_user_id:
        status = "accepted"
    elif i.expires <= now:
        status = "expired"
    else:
        status = "pending"
    return {"id": i.id, "email": i.email, "invited_by": i.invited_by,
           "invited_at": i.invited_at, "expires": i.expires, "status": status,
           "grants": [{"scope": g.scope, "mode": g.mode} for g in i.grants]}


@users_router.post("/users/invite", status_code=201)
def invite_user(request: Request, body: dict = Body(...),
               auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
               admin: User = Depends(require_admin)) -> dict:
    email = (body.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(422, "a valid email is required")
    if repo.find_user_by_email(auth, email) is not None:
        raise HTTPException(409, f"'{email}' is already a user")
    if repo.find_pending_invite_by_email(auth, email) is not None:
        raise HTTPException(409, f"an invitation is already pending for '{email}'")
    grants = _parse_grants(body.get("grants") or [])
    login_url = f"{public_origin(request)}/login"
    invitation = invites.create_invitation(repo, auth, email=email, grants=grants,
                                           invited_by=admin, login_url=login_url)
    return {**_invite_out(invitation.invite), "link": invitation.link,
           "emailed": invitation.emailed}


@users_router.get("/invites")
def list_invites(auth: AuthContext = Depends(get_auth), repo: Repository = Depends(get_repository),
                 admin: User = Depends(require_admin)) -> list[dict]:
    return [_invite_out(i) for i in repo.list_invites(auth)]


@users_router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite_route(invite_id: str, auth: AuthContext = Depends(get_auth),
                        repo: Repository = Depends(get_repository),
                        admin: User = Depends(require_admin)) -> None:
    try:
        result = invites.revoke_invitation(repo, auth, invite_id)
    except ConsentRequired as exc:
        # Same gate, same envelope shape as remove_user_route: revoking an
        # accepted invite removes the user behind it (auth/invites.py), and
        # deleting the invite record itself is also consent-gated.
        raise HTTPException(409, {
            "error": "consent_required",
            "message": "Revoking this invitation needs approval in datahive.",
            "request_id": exc.request_id, "target": exc.target,
            "approve": exc.envelope.get("approval_urls", {}),
        }) from exc
    if isinstance(result, users.LastAdminRefused):
        raise HTTPException(409, result.reason)


__all__ = ["users_router"]
