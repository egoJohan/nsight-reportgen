"""No route serves data without resolving a user.

What this holds is that a route ADDED LATER cannot quietly skip the check.
Whoever adds one either declares a guard or writes themselves into
PUBLIC_ROUTES, in a diff a reviewer can see. There is no runtime symptom when
a route forgets — it just serves the whole tenant.
"""
import pathlib

import pytest

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
        "/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc",
        # Whether the deployment can serve at all. Public because it must
        # answer while a session is dead and while the hive is away — the two
        # moments it exists for — and it discloses nothing beyond "up" or
        # "not now". The browser polls it to know when to take the maintenance
        # screen down.
        "/readyz",
        "/auth/logout", "/signup/me", "/signup-requests",
        "/auth/login/{provider}", "/auth/callback/{provider}", "/auth/providers"})


# --------------------------------------------------------------------------- #
# The two proxies in front of the API
# --------------------------------------------------------------------------- #
# The browser never talks to the backend directly: vite proxies in dev, nginx
# in the image, and each has its own hand-maintained list of path prefixes. A
# prefix missing from either does not fail loudly — the SPA's catch-all answers
# instead, so `fetch("/signup/me")` gets index.html and the page decides the
# call failed. That is how a working feature reached a browser and did nothing.

_DOC_ROUTES = {"/health", "/openapi.json", "/docs", "/redoc"}


def _api_prefixes() -> set[str]:
    """The first path segment of every real API route."""
    out = set()
    for route in create_app().routes:
        path = getattr(route, "path", "")
        if not path.startswith("/") or not hasattr(route, "dependant"):
            continue
        if path in _DOC_ROUTES or path.startswith("/docs"):
            continue
        head = path.split("/")[1]
        if head and not head.startswith("{"):
            out.add("/" + head)
    return out


@pytest.mark.parametrize("proxy", ["web/vite.config.ts", "web/nginx.conf"])
def test_every_api_prefix_is_proxied(proxy):
    """Both proxy lists must name every prefix the API serves."""
    root = pathlib.Path(__file__).resolve().parents[4]
    text = (root / proxy).read_text(encoding="utf-8")
    missing = sorted(p for p in _api_prefixes() if f"'{p}'" not in text
                     and f" {p} " not in text and f"{p} " not in text)
    assert missing == [], (
        f"{proxy} does not proxy {missing}. The SPA catch-all will answer "
        f"these with index.html and the caller will read HTML as JSON.")
