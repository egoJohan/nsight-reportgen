"""Access requests: the admin-actionable half of "Request access" on the
no-access customer page.

A signed-in user who has no grant on a customer 404s out of every
customer-scoped route in routes_customers.py (spec §5, `deps_auth._check`) --
that stays exactly as it is. This file is the one place such a user may
still act: filing a request that NAMES the customer they were just refused,
so it lands somewhere an admin can see and decide it. Nothing here reads the
customer's data, and filing a request never itself grants anything -- only
`approve_access_request` below touches a grant, and it does so by reusing
`Repository.set_grants`, the exact write `PUT /users/{id}/grants`
(routes_users.py) and `ManagePermissionsDialog` already perform, not a
second grant-writing path.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from reportbuilder.api.deps_auth import current_user, require_admin
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import EDIT, VIEW, Grant, User, may_read, may_write
from reportbuilder.store.repository import AccessRequest, Repository
from reportbuilder.store.seam import AuthContext, NotFound

access_requests_router = APIRouter(tags=["access-requests"])


class AccessRequestBody(BaseModel):
    customer_id: str = Field(min_length=1)
    mode: str = Field(min_length=1)


def _request_out(repo: Repository, auth: AuthContext, r: AccessRequest) -> dict:
    """A request plus the customer's name, the same courtesy `_grant_out`
    (routes_users.py) gives a grant -- an admin's queue should read
    "Attendo · edit", not a bare customer id. Looked up with `user=None`
    (repo.find_customer's default): this route is reached only by
    `require_admin` or by the requester asking about their OWN request, and
    the point of the request is that they may not otherwise see this
    customer at all, so the grant filter that protects other routes would
    just make an admin's own queue unreadable here.
    """
    customer = repo.find_customer(auth, r.customer_id)
    return {"id": r.id, "user_id": r.user_id, "user_email": r.user_email,
           "customer_id": r.customer_id,
           "customer_name": customer.name if customer is not None else None,
           "mode": r.mode, "requested_at": r.requested_at, "state": r.state,
           "decided_by": r.decided_by, "decided_at": r.decided_at}


@access_requests_router.post("/access-requests", status_code=201)
def create_access_request(body: AccessRequestBody,
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
                         admin: User = Depends(require_admin)) -> list[dict]:
    """Every request, newest first -- pending ones an admin still has to act
    on, and past decisions for context. Settings > Users is where this
    surfaces (see SettingsPage.tsx), beside Users and Invitations."""
    return [_request_out(repo, auth, r) for r in repo.list_access_requests(auth)]


@access_requests_router.post("/access-requests/{request_id}/approve")
def approve_access_request(request_id: str, auth: AuthContext = Depends(get_auth),
                           repo: Repository = Depends(get_repository),
                           admin: User = Depends(require_admin)) -> dict:
    """Grant exactly what was asked, and only that: the request's own
    `mode`, never anything wider a caller might try to smuggle in -- this
    route takes no body, so there is nothing to smuggle.

    An admin may not approve their OWN request. `require_admin` already
    stops a non-admin from reaching this route at all, so the only way
    "approve your own request" is reachable is an admin approving something
    they themselves filed -- which would make the whole review step
    theatre: file a request, immediately rubber-stamp it with the same
    identity that filed it. Somebody else with admin rights has to be the
    one who looks at it.
    """
    r = repo.get_access_request(auth, request_id)
    if r is None:
        raise HTTPException(404, f"Access request '{request_id}' not found")
    if r.state != "pending":
        raise HTTPException(409, f"Already {r.state}")
    if r.user_id == admin.id:
        raise HTTPException(403, "You cannot approve your own request")
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
    decided = repo.decide_access_request(auth, request_id, "granted", admin.id)
    return _request_out(repo, auth, decided)


@access_requests_router.post("/access-requests/{request_id}/refuse")
def refuse_access_request(request_id: str, auth: AuthContext = Depends(get_auth),
                          repo: Repository = Depends(get_repository),
                          admin: User = Depends(require_admin)) -> dict:
    r = repo.get_access_request(auth, request_id)
    if r is None:
        raise HTTPException(404, f"Access request '{request_id}' not found")
    if r.state != "pending":
        raise HTTPException(409, f"Already {r.state}")
    decided = repo.decide_access_request(auth, request_id, "refused", admin.id)
    return _request_out(repo, auth, decided)


__all__ = ["access_requests_router"]
