"""GET /auth/login/{provider} and /auth/callback/{provider}, against a fake
IdP (same technique as test_oidc.py) -- proving the HTTP wiring, not the
crypto (that's Task 11's job).
"""
import time
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from joserfc import jwk as joserfc_jwk
from joserfc import jwt as joserfc_jwt

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import oidc
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration

ISSUER = "https://fake-idp.example/"
CLIENT_ID = "test-client-id"


@pytest.fixture
def rsa_key():
    return joserfc_jwk.RSAKey.generate_key(2048, parameters={"kid": "test-1"})


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture(autouse=True)
def _configured(repo, auth, monkeypatch):
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}})
    monkeypatch.setitem(oidc._METADATA_URL, "google", f"{ISSUER}.well-known/openid-configuration")


@pytest.fixture
def client(repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    # https, not the TestClient default http://testserver: both cookies this
    # flow sets (nsight_oauth, nsight_session) are Secure, and a Secure
    # cookie is never sent back over plain http -- same fix as
    # test_sign_in_flow.py / test_current_user_session.py.
    return TestClient(app, base_url="https://testserver")


def _id_token(rsa_key, nonce, *, email="maija@egoiq.com", email_verified=True):
    now = int(time.time())
    claims = {"iss": ISSUER, "aud": CLIENT_ID, "sub": "user-123", "email": email,
             "email_verified": email_verified, "iat": now, "exp": now + 3600, "nonce": nonce}
    return joserfc_jwt.encode({"alg": "RS256", "kid": "test-1"}, claims, rsa_key)


def _fake_idp_transport(rsa_key, nonce_box: dict):
    # rsa_key.as_dict() defaults to private=False, i.e. exactly the public
    # JWK a real provider would publish at its jwks_uri (see test_oidc.py).
    jwks = {"keys": [rsa_key.as_dict()]}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}auth",
                "token_endpoint": f"{ISSUER}token", "jwks_uri": f"{ISSUER}jwks"})
        if request.url.path == "/jwks":
            return httpx.Response(200, json=jwks)
        if request.url.path == "/token":
            return httpx.Response(200, json={
                "access_token": "at-1", "token_type": "Bearer",
                "id_token": _id_token(rsa_key, nonce_box["nonce"])})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_login_redirects_to_the_provider_and_sets_the_oauth_cookie(client, monkeypatch, rsa_key):
    monkeypatch.setattr(oidc, "begin", lambda *a, **k: _AsyncResult((
        f"{ISSUER}auth?client_id={CLIENT_ID}", "state-1", "nonce-1")))
    r = client.get("/auth/login/google", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"].startswith(ISSUER)
    assert r.cookies.get("nsight_oauth")


def test_an_unconfigured_provider_is_503(client):
    r = client.get("/auth/login/microsoft", follow_redirects=False)
    assert r.status_code == 503


def test_the_full_round_trip_signs_the_user_in(client, monkeypatch, rsa_key):
    # identity.resolve_signed_in_user refuses anyone who is neither an
    # existing user, a bootstrap admin, nor on an allowed domain (see
    # test_a_verified_email_that_matches_nothing_is_refused_not_signed_in,
    # right below, for that path) -- this is what lets THIS verified email
    # actually resolve to a user, same pattern as test_auth_password.py's
    # bootstrap-admin fixture.
    monkeypatch.setenv("NSIGHT_BOOTSTRAP_ADMINS", "maija@egoiq.com")
    nonce_box = {"nonce": None}
    transport = _fake_idp_transport(rsa_key, nonce_box)
    monkeypatch.setattr(oidc, "_client",
                        lambda config, redirect_uri, _ignored: oidc.AsyncOAuth2Client(
                            config.client_id, config.client_secret, scope=oidc._SCOPE,
                            redirect_uri=redirect_uri, transport=transport))

    login = client.get("/auth/login/google", follow_redirects=False)
    parsed = urlparse(login.headers["location"])
    nonce_box["nonce"] = parse_qs(parsed.query)["nonce"][0]
    state = parse_qs(parsed.query)["state"][0]

    callback = client.get(f"/auth/callback/google?code=fake-code&state={state}",
                          follow_redirects=False)
    assert callback.status_code == 302
    assert client.cookies.get("nsight_session")
    assert not client.cookies.get("nsight_oauth")

    me = client.get("/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "maija@egoiq.com"


def test_a_state_mismatch_is_rejected(client):
    client.cookies.set("nsight_oauth", "garbage")
    r = client.get("/auth/callback/google?code=fake-code&state=whatever")
    assert r.status_code == 400


def test_a_verified_email_that_matches_nothing_is_refused_not_signed_in(client, monkeypatch, rsa_key):
    nonce_box = {"nonce": None}
    transport = _fake_idp_transport(rsa_key, nonce_box)
    monkeypatch.setattr(oidc, "_client",
                        lambda config, redirect_uri, _ignored: oidc.AsyncOAuth2Client(
                            config.client_id, config.client_secret, scope=oidc._SCOPE,
                            redirect_uri=redirect_uri, transport=transport))
    # No bootstrap admin, no allowed domain configured for this test.
    login = client.get("/auth/login/google", follow_redirects=False)
    parsed = urlparse(login.headers["location"])
    nonce_box["nonce"] = parse_qs(parsed.query)["nonce"][0]
    state = parse_qs(parsed.query)["state"][0]

    callback = client.get(f"/auth/callback/google?code=fake-code&state={state}",
                          follow_redirects=False)
    assert callback.status_code == 302
    assert "/login" in callback.headers["location"]
    assert not client.cookies.get("nsight_session")


class _AsyncResult:
    """Wraps a plain value so `await oidc.begin(...)` works in a test that
    replaces `begin` with a synchronous stub."""
    def __init__(self, value):
        self._value = value
    def __await__(self):
        async def _coro():
            return self._value
        return _coro().__await__()
