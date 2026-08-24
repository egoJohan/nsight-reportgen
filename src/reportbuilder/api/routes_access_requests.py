"""Access requests: the admin/owner-actionable half of "Request access" on
the no-access customer page.

A signed-in user who has no grant on a customer 404s out of every
customer-scoped route in routes_customers.py (spec §5, `deps_auth._check`) --
that stays exactly as it is. This file is the one place such a user may
still act: filing a request that NAMES the customer they were just refused,
so it lands somewhere an admin, or that customer's own owner, can see and
decide it. Nothing here reads the customer's data, and filing a request
never itself grants anything -- only `approve_access_request` below touches
a grant, and it does so by reusing `Repository.set_grants`, the exact write
`PUT /users/{id}/grants` (routes_users.py) and `ManagePermissionsDialog`
already perform, not a second grant-writing path.

"Owner" is not a role of its own -- the grant model only knows `view` and
`edit` (auth/permissions.py) -- it means holding `edit` on the customer a
request names. `_require_decider` is the one place that rule lives; deciding
who may SEE the queue (`list_access_requests`) reuses the same `may_write`
check rather than a second definition of "owns this customer".
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.api.routes_auth import public_origin
from reportbuilder.auth import access_request_mail
from reportbuilder.auth import session
from reportbuilder.auth.permissions import EDIT, VIEW, Grant, User, may_read, may_write
from reportbuilder.store.repository import AccessRequest, Repository
from reportbuilder.store.seam import AuthContext, NotFound

access_requests_router = APIRouter(tags=["access-requests"])


class AccessRequestBody(BaseModel):
    customer_id: str = Field(min_length=1)
    mode: str = Field(min_length=1)


def _request_out(repo: Repository, auth: AuthContext, r: AccessRequest) -> dict:
    """A request plus the customer's name, the same courtesy `_grant_out`
    (routes_users.py) gives a grant -- an admin's or an owner's queue should
    read "Attendo · edit", not a bare customer id. Looked up with `user=None`
    (repo.find_customer's default): every caller who reaches a row here --
    an admin, an owner reading their own customer's queue, or the requester
    asking about their OWN request -- is someone the ordinary grant filter
    would otherwise block from seeing this customer at all (that's the
    point of filing a request), so applying it here would just make the
    queue unreadable to the people meant to read it.
    """
    customer = repo.find_customer(auth, r.customer_id)
    return {"id": r.id, "user_id": r.user_id, "user_email": r.user_email,
           "customer_id": r.customer_id,
           "customer_name": customer.name if customer is not None else None,
           "mode": r.mode, "requested_at": r.requested_at, "state": r.state,
           "decided_by": r.decided_by, "decided_at": r.decided_at}


@access_requests_router.post("/access-requests", status_code=201)
def create_access_request(body: AccessRequestBody, request: Request,
                          auth: AuthContext = Depends(get_auth),
                          repo: Repository = Depends(get_repository),
                          user: User = Depends(current_user)) -> dict:
    """File a request for the caller's OWN account.

    Cannot become a request-on-behalf-of-someone-else: the requester is
    always `current_user`'s id, taken from the session, never from the
    request body -- there is no field here naming who the request is for.
    Cannot become a self-grant either: this only ever writes an
    AccessRequest row, never a Grant -- `create_access_request` (the
    Repository method) touches no grant, so filing a request grants nothing
    by itself, no matter who files it or what mode they ask for.

    Best-effort emails whoever could decide it (admins, and any owner of
    THIS customer -- access_request_mail.decision_makers, kept in exact
    lockstep with `_require_decider` below) once the record exists. Never
    on the critical path: a mail failure, or nobody configured to send at
    all, still leaves the request filed -- see notify_decision_makers.
    """
    if body.mode not in (VIEW, EDIT):
        raise HTTPException(422, "mode must be 'view' or 'edit'")
    try:
        customer = repo.get_customer(auth, body.customer_id)
    except NotFound:
        raise HTTPException(404, f"Customer '{body.customer_id}' not found") from None
    already = may_write(user, customer.id) if body.mode == EDIT else may_read(user, customer.id)
    if already:
        raise HTTPException(409, f"You already have {body.mode} access to '{customer.name}'")
    r = repo.create_access_request(auth, user_id=user.id, user_email=user.email,
                                   customer_id=customer.id, mode=body.mode)
    settings_url = f"{public_origin(request)}/settings?tab=permission-requests"
    access_request_mail.notify_decision_makers(
        repo, auth, request=r, customer_name=customer.name, settings_url=settings_url)
    return _request_out(repo, auth, r)


@access_requests_router.get("/access-requests/mine")
def list_my_access_requests(auth: AuthContext = Depends(get_auth),
                            repo: Repository = Depends(get_repository),
                            user: User = Depends(current_user)) -> list[dict]:
    """Only the caller's own requests. This is deliberately NOT filtered by
    admin-ness -- it exists so the no-access page can show "you already
    asked, pending" on a later visit -- but it is filtered to `user.id`
    regardless of who is asking, so it never becomes a way to browse
    somebody else's requests. `GET /access-requests` below is the admin
    queue that sees everyone's."""
    return [_request_out(repo, auth, r)
            for r in repo.list_access_requests_for_user(auth, user.id)]


@access_requests_router.get("/access-requests")
def list_access_requests(auth: AuthContext = Depends(get_auth),
                         repo: Repository = Depends(get_repository),
                         user: User = Depends(current_user)) -> list[dict]:
    """The queue: PENDING requests only. An admin sees every one; a
    customer's owner (`edit` -- see the module docstring) sees only the
    ones naming customers they own; a plain viewer, or someone with no
    grant at all, gets `[]` -- not a 403, because having nothing to decide
    is not being refused a permission.

    Decided requests (granted/refused) never appear here -- they are
    history, not queue. The record itself (state, decided_by, decided_at)
    is untouched; this route just stops shipping it to a screen that has
    nothing left to do with it. `GET /access-requests/mine` is the other
    listing, and stays unfiltered by state for exactly that reason -- the
    no-access page needs "you already asked, refused" too, not just
    pending. Settings > Permission requests is where this surfaces (see
    SettingsPage.tsx)."""
    rows = [r for r in repo.list_access_requests(auth) if r.state == "pending"]
    if not user.is_admin:
        rows = [r for r in rows if may_write(user, r.customer_id)]
    return [_request_out(repo, auth, r) for r in rows]


def _require_decider(user: User, r: AccessRequest) -> None:
    """Admin, or the customer's owner deciding a request for their OWN
    customer -- see the module docstring for why `edit` is what "owner"
    means here. Anyone else is refused outright, before anything about the
    request is revealed.

    There is deliberately no rule here banning a caller from deciding their
    OWN request. There used to be one; it was removed because it protected
    against nothing an admin could not already do in two clicks through
    `PUT /users/{id}/grants` (ManagePermissionsDialog on the customer page),
    while creating a genuine dead end: a request filed by the tenant's only
    admin could never be approved by anyone. This scope check is what
    actually stands between a request and an escalation -- someone with
    `edit` on Attendo cannot approve their own request for Synsam, because
    they hold no `edit` on Synsam, regardless of who filed it.
    """
    if user.is_admin or may_write(user, r.customer_id):
        return
    raise HTTPException(403, "You may not decide requests for this customer")


@access_requests_router.post("/access-requests/{request_id}/approve")
def approve_access_request(request_id: str, auth: AuthContext = Depends(get_auth),
                           repo: Repository = Depends(get_repository),
                           user: User = Depends(current_user)) -> dict:
    """Grant exactly what was asked, and only that: the request's own
    `mode`, never anything wider a caller might try to smuggle in -- this
    route takes no body, so there is nothing to smuggle. See
    `_require_decider` for who may reach past the checks below.
    """
    r = repo.get_access_request(auth, request_id)
    if r is None:
        raise HTTPException(404, f"Access request '{request_id}' not found")
    if r.state != "pending":
        raise HTTPException(409, f"Already {r.state}")
    _require_decider(user, r)
    target = repo.get_user(auth, r.user_id)
    if target is None:
        raise HTTPException(404, "The requesting user no longer exists")
    # The same merge `ManagePermissionsDialog.writeGrant` performs client-side
    # before calling PUT /users/{id}/grants: keep every OTHER scope this user
    # already holds untouched, and only replace (or add) the entry for THIS
    # customer. `set_grants` replaces the whole list, so skipping this merge
    # would silently strip every other customer this person can already see.
    rest = [g for g in target.grants if g.scope != r.customer_id]
    repo.set_grants(auth, r.user_id, [*rest, Grant(r.customer_id, r.mode)])
    # So the person who asked sees the customer on their next click rather than
    # within the identity cache's TTL. They are almost certainly watching.
    session.forget_user(r.user_id)
    decided = repo.decide_access_request(auth, request_id, "granted", user.id)
    return _request_out(repo, auth, decided)


@access_requests_router.post("/access-requests/{request_id}/refuse")
def refuse_access_request(request_id: str, auth: AuthContext = Depends(get_auth),
                          repo: Repository = Depends(get_repository),
                          user: User = Depends(current_user)) -> dict:
    r = repo.get_access_request(auth, request_id)
    if r is None:
        raise HTTPException(404, f"Access request '{request_id}' not found")
    if r.state != "pending":
        raise HTTPException(409, f"Already {r.state}")
    _require_decider(user, r)
    decided = repo.decide_access_request(auth, request_id, "refused", user.id)
    return _request_out(repo, auth, decided)


__all__ = ["access_requests_router"]
