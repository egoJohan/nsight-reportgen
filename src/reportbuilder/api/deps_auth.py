"""Turning a request into a user, and a user into an answer.

`current_user` is the seam: everything below it asks the permission model,
not the request, and does not change when the way a user gets identified
does.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Request

from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import session as _session
from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.auth.permissions import User, may_read, may_write
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

#: Routes that serve no customer data. Anything else must resolve a user — see
#: tests/suite/integration/api/test_route_census.py.
PUBLIC_ROUTES = frozenset({"/health", "/openapi.json", "/docs",
                           "/docs/oauth2-redirect", "/redoc",
                           "/auth/register", "/auth/login/password", "/auth/logout",
                           # Necessarily public: these ARE how a user becomes
                           # known to nSight in the first place -- nothing
                           # is served here but a redirect to the provider,
                           # or a session mint gated by
                           # identity.resolve_signed_in_user.
                           "/auth/login/{provider}", "/auth/callback/{provider}",
                           # Also necessarily public: the signed-out login page's
                           # only way to know which SSO buttons to offer.
                           # Presence only -- see routes_auth.auth_providers --
                           # never a client id, secret, or anything else
                           # /settings/oidc (admin-only) guards.
                           "/auth/providers"})


def current_user(request: Request,
                 auth: AuthContext = Depends(get_auth),
                 repo: Repository = Depends(get_repository)) -> User:
    """The signed-in user, resolved from the session cookie (spec §4, §7).

    No fallback. A request with no cookie, a malformed one, or a session that
    has expired or been revoked all get 401. There is no dev bypass — tests
    that need an authenticated request override THIS dependency via
    `app.dependency_overrides`, the same way they already override
    `get_auth`/`get_repository` (see tests/suite/_helpers.sign_in_override).
    """
    raw = request.cookies.get(_session.COOKIE_NAME)
    if not raw:
        raise HTTPException(401, "Not signed in")
    key = get_or_create_signing_key(repo, auth)
    session_id = _session.session_id_from_cookie(key, raw)
    if session_id is None:
        raise HTTPException(401, "Invalid session")
    user = _session.resolve(repo, auth, session_id)
    if user is None:
        raise HTTPException(401, "Session expired or signed out")
    return user


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
    """The customer-addressed routes.

    Same shape as `_case_guard`/`_material_guard`: resolve the id first, 404 if
    it does not exist, THEN ask the permission question. Checking the grant
    against a raw, unresolved id would answer 403 for a customer that was never
    there, which claims to know something it does not — a write route's 403
    means "you can already see this, you just may not change it", and that is
    false for a nonexistent customer.
    """
    def guard(customer_id: str,
              user: User = Depends(current_user),
              auth: AuthContext = Depends(get_auth),
              repo: Repository = Depends(get_repository)) -> User:
        customer = repo.find_customer(auth, customer_id, user=user)
        if customer is None:
            raise HTTPException(404, f"Customer '{customer_id}' not found")
        _check(user, customer.id, write)
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


def _case_in_customer_guard(write: bool):
    """For routes addressed by BOTH ids — /customers/{c}/cases/{k}/…

    The case id is what authorises; the customer id then ADDRESSES storage. So
    the two have to be the same customer, and nothing checked that they were: a
    caller with a grant on one customer's case could pass ANY customer id
    alongside it and have the route read and write under that customer's tree.
    It leaked template names across customers, and the report-binding PUT wrote
    a report doc into the other customer's path.

    A mismatch is a 404, not a 403: the pair does not exist, and saying "you may
    not" would confirm that the customer does.
    """
    def guard(customer_id: str, case_id: str,
              user: User = Depends(current_user),
              auth: AuthContext = Depends(get_auth),
              repo: Repository = Depends(get_repository)) -> User:
        case = repo.find_case(auth, case_id, user=user)
        if case is None or case.customer_id != customer_id:
            raise HTTPException(404, f"Case '{case_id}' not found")
        _check(user, f"{case.customer_id}/{case.id}", write)
        return user
    guard.__name__ = ("require_case_in_customer_write" if write
                      else "require_case_in_customer")
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
require_case_in_customer = _case_in_customer_guard(False)
require_case_in_customer_write = _case_in_customer_guard(True)
require_material = _material_guard(False)
require_material_write = _material_guard(True)

#: What the census recognises as "this route resolved a user".
GUARD_NAMES = frozenset({
    "current_user", "require_admin",
    "require_customer", "require_customer_write",
    "require_case", "require_case_write",
    "require_case_in_customer", "require_case_in_customer_write",
    "require_material", "require_material_write",
})
