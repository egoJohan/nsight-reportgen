"""No route serves data without resolving a user.

What this holds is that a route ADDED LATER cannot quietly skip the check.
Whoever adds one either declares a guard or writes themselves into
PUBLIC_ROUTES, in a diff a reviewer can see. There is no runtime symptom when
a route forgets — it just serves the whole tenant.
"""
from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import GUARD_NAMES, PUBLIC_ROUTES


def _guarded(route) -> bool:
    """True when one of this route's dependencies resolves a user."""
    return any(getattr(d.call, "__name__", "") in GUARD_NAMES
               for d in route.dependant.dependencies)


def test_every_route_is_guarded_or_explicitly_public():
    app = create_app()
    unguarded = [
        f"{sorted(getattr(route, 'methods', []))} {route.path}"
        for route in app.routes
        if hasattr(route, "dependant")
        and route.path not in PUBLIC_ROUTES
        and not _guarded(route)
    ]
    assert unguarded == [], (
        "these routes resolve no user — add a guard from deps_auth, or list "
        "them in PUBLIC_ROUTES with a reason:\n  " + "\n  ".join(sorted(unguarded)))


def test_public_routes_are_few_and_named():
    """A growing public list is the failure this test exists to make visible."""
    assert PUBLIC_ROUTES == frozenset({
        "/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})
