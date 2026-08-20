"""Turning a request into a user, and a user into an answer.

Plan 2 adds sign-in. Until then `current_user` resolves a development user, and
it is the ONLY function in this file that changes when the session cookie
arrives — everything below it asks the permission model, not the request.
"""
from __future__ import annotations

import os

from fastapi import Depends, HTTPException, Request

from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import Grant, User, may_read, may_write
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

#: Routes that serve no customer data. Anything else must resolve a user — see
#: tests/suite/integration/api/test_route_census.py.
PUBLIC_ROUTES = frozenset({"/health", "/openapi.json", "/docs",
                           "/docs/oauth2-redirect", "/redoc"})


def current_user(request: Request,
                 auth: AuthContext = Depends(get_auth),
                 repo: Repository = Depends(get_repository)) -> User:
    """The user this request acts as.

    DEVELOPMENT STAND-IN. `NSIGHT_DEV_USER` names an email that must already
    exist in the store; without it the request is an admin granted every
    customer, which is exactly today's pre-login behaviour, so nothing that
    works now stops working. Plan 2 replaces this body with a session lookup
    and deletes the environment variable.
    """
    email = os.environ.get("NSIGHT_DEV_USER", "").strip()
    if email:
        user = repo.find_user_by_email(auth, email)
        if user is None:
            raise HTTPException(401, f"NSIGHT_DEV_USER '{email}' is not a known user")
        return user
    return User(id="dev", email="dev@localhost", name="Development",
                is_admin=True,
                grants=tuple(Grant(c.id, "edit") for c in repo.list_customers(auth)))


def require_admin(user: User = Depends(current_user)) -> User:
    """Managing users and tenant-wide settings. Not a data grant (spec §5)."""
    if not user.is_admin:
        raise HTTPException(403, "Admin only")
    return user


def _check(user: User, path: str, write: bool) -> None:
    if (may_write if write else may_read)(user, path):
        return
    # A read you may not do is 404, not 403: a 403 confirms the object exists,
    # which is what "never leak the existence of an out-of-scope path" forbids.
    # A write is 403 — you can already see the thing, you just may not change it.
    raise HTTPException(403 if write else 404, "Not found")


def _customer_guard(write: bool):
    def guard(customer_id: str, user: User = Depends(current_user)) -> User:
        _check(user, customer_id, write)
        return user
    guard.__name__ = "require_customer_write" if write else "require_customer"
    return guard


def _case_guard(write: bool):
    def guard(case_id: str,
              user: User = Depends(current_user),
              auth: AuthContext = Depends(get_auth),
              repo: Repository = Depends(get_repository)) -> User:
        case = repo.find_case(auth, case_id, user=user)
        if case is None:
            raise HTTPException(404, f"Case '{case_id}' not found")
        _check(user, f"{case.customer_id}/{case.id}", write)
        return user
    guard.__name__ = "require_case_write" if write else "require_case"
    return guard


def _material_guard(write: bool):
    """The material-addressed routes (spec §5.1).

    A material id is not authorisation: resolve it to its case and customer and
    ask the same question every other route asks. `find_material` already
    returns None for a material the user may not see, so the 404 arrives before
    any SAV is read.
    """
    def guard(material_id: str,
              user: User = Depends(current_user),
              auth: AuthContext = Depends(get_auth),
              repo: Repository = Depends(get_repository)) -> User:
        material = repo.find_material(auth, material_id, user=user)
        if material is None:
            raise HTTPException(404, f"Material '{material_id}' not found")
        _check(user, f"{material.customer_id}/{material.case_id}", write)
        return user
    guard.__name__ = "require_material_write" if write else "require_material"
    return guard


require_customer = _customer_guard(False)
require_customer_write = _customer_guard(True)
require_case = _case_guard(False)
require_case_write = _case_guard(True)
require_material = _material_guard(False)
require_material_write = _material_guard(True)

#: What the census recognises as "this route resolved a user".
GUARD_NAMES = frozenset({
    "current_user", "require_admin",
    "require_customer", "require_customer_write",
    "require_case", "require_case_write",
    "require_material", "require_material_write",
})
