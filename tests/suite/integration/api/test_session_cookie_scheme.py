"""The session cookie has to come back.

`secure=True` was hardcoded. Over plain HTTP the browser accepts the Set-Cookie
and then declines to ever send it: signing in looks like it worked, and every
request after it is anonymous. That is every deployment reached by LAN address
or bare hostname without TLS — which is what a product test runs on.

Nothing is traded away for it. A Secure cookie on http is not protection, it is
a cookie that never arrives; where there IS TLS the flag is still set.
"""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration

CREDS = {"email": "admin@egoiq.com", "password": "correct horse battery staple"}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NSIGHT_BOOTSTRAP_ADMINS", "admin@egoiq.com")
    monkeypatch.delenv("NSIGHT_PUBLIC_URL", raising=False)
    app = create_app()
    repo = Repository(InMemoryObjectStore())
    auth = AuthContext(token="test")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    # Deliberately NOT overriding current_user: the real cookie round-trip is
    # the thing under test, and httpx's cookie jar applies the Secure rule the
    # same way a browser does — it will not return a Secure cookie over http.
    return TestClient(app)


def _session_cookie(response) -> str:
    header = next(v for k, v in response.headers.raw
                  if k.decode().lower() == "set-cookie"
                  and v.decode().startswith("nsight_session="))
    return header.decode()


def test_over_plain_http_the_cookie_is_one_the_browser_will_send_back(client):
    cookie = _session_cookie(client.post("/auth/register", json=CREDS))
    assert "Secure" not in cookie
    # The protections that DO work over http are not relaxed with it.
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie


def test_under_tls_it_is_still_secure(client, monkeypatch):
    monkeypatch.setenv("NSIGHT_PUBLIC_URL", "https://nsight.example.com")
    assert "Secure" in _session_cookie(client.post("/auth/register", json=CREDS))


def test_the_signed_in_session_actually_works_over_plain_http(client):
    """The point of the whole thing: a second request is still signed in."""
    assert client.post("/auth/register", json=CREDS).status_code == 201
    me = client.get("/auth/me")
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "admin@egoiq.com"


def test_the_oidc_handshake_cookie_follows_the_same_rule(client, monkeypatch):
    """It is set on the way OUT to the provider and read on the way back; a
    cookie the browser refuses to return breaks the state/nonce check.

    The provider is seeded through the SETTINGS STORE, which is where OIDC
    config lives. An earlier version set NSIGHT_GOOGLE_* environment variables
    — names that appear nowhere in src/ — so /auth/login/google answered 503
    and the skip below fired 100 % of the time, here and everywhere.
    """
    from reportbuilder.api.deps_store import get_auth, get_repository
    from reportbuilder.auth import oidc

    monkeypatch.setenv("NSIGHT_PUBLIC_URL", "https://nsight.example.com")
    overrides = client.app.dependency_overrides
    repo, auth = overrides[get_repository](), overrides[get_auth]()
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": "cid", "client_secret": "sec"}})
    monkeypatch.setattr(
        oidc, "begin",
        lambda *a, **k: _Resolved(("https://accounts.example/auth", "st", "no")))

    r = client.get("/auth/login/google", follow_redirects=False)
    assert r.status_code == 302, f"the provider was not configured: {r.text[:120]}"
    cookie = next(v.decode() for k, v in r.headers.raw
                  if k.decode().lower() == "set-cookie")
    assert "nsight_oauth=" in cookie
    assert "Secure" in cookie


class _Resolved:
    """`oidc.begin` is awaited; this stands in without a provider round trip."""

    def __init__(self, value):
        self._value = value

    def __await__(self):
        async def _v():
            return self._value
        return _v().__await__()
