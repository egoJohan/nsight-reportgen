"""GET /auth/login/{provider} and /auth/callback/{provider}, against a fake
IdP (same technique as test_oidc.py) -- proving the HTTP wiring, not the
crypto (that's Task 11's job).
"""
import time
from urllib.parse import parse_qs, quote, urlparse

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


def test_a_corrupt_oauth_cookie_is_rejected(client):
    """Not a genuine state mismatch -- "garbage" never survives
    `_oauth_codec(...).loads` far enough to reach the state comparison at
    all; it fails to decode first. See test_oidc_failure_modes.py's
    test_a_genuine_state_mismatch_against_a_validly_signed_cookie_is_rejected
    for the actual CSRF-mismatch branch, against a validly-signed cookie."""
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
    # Not signed in, and sent somewhere they can ask rather than to a dead end.
    # The distinction that matters is the cookie: a signup ticket says a
    # provider vouched for this address, NOT that nSight has an account for it.
    assert callback.headers["location"] == "/request-access"
    assert not client.cookies.get("nsight_session")
    assert client.cookies.get("nsight_signup")


def _capture_redirect_uri(monkeypatch):
    """Replaces oidc.begin with a stub that records the redirect_uri it was
    given -- same technique as
    test_login_redirects_to_the_provider_and_sets_the_oauth_cookie, but
    keeping the argument instead of throwing it away."""
    captured: dict = {}

    def _begin(repo, auth, provider, redirect_uri):
        captured["redirect_uri"] = redirect_uri
        return _AsyncResult((f"{ISSUER}auth", "state-1", "nonce-1"))

    monkeypatch.setattr(oidc, "begin", _begin)
    return captured


def test_the_callback_url_uses_forwarded_headers_when_the_request_is_trusted(client, monkeypatch):
    # The TestClient's default client address ("testclient") is one of the
    # trusted hosts (see routes_auth._trust_forwarded_headers) -- this is
    # the Vite/nginx-in-front-of-the-backend path task-12b fixes.
    captured = _capture_redirect_uri(monkeypatch)
    r = client.get("/auth/login/google", follow_redirects=False,
                   headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "localhost:5180"})
    assert r.status_code == 302
    assert captured["redirect_uri"] == "https://localhost:5180/auth/callback/google"


def test_nsight_public_url_wins_over_forwarded_headers(client, monkeypatch):
    captured = _capture_redirect_uri(monkeypatch)
    monkeypatch.setenv("NSIGHT_PUBLIC_URL", "https://nsight.egohive.ai")
    r = client.get("/auth/login/google", follow_redirects=False,
                   headers={"X-Forwarded-Proto": "http", "X-Forwarded-Host": "evil.example"})
    assert r.status_code == 302
    assert captured["redirect_uri"] == "https://nsight.egohive.ai/auth/callback/google"


def test_with_neither_forwarded_headers_nor_override_the_old_behaviour_holds(client, monkeypatch):
    captured = _capture_redirect_uri(monkeypatch)
    r = client.get("/auth/login/google", follow_redirects=False)
    assert r.status_code == 302
    assert captured["redirect_uri"] == "https://testserver/auth/callback/google"


def test_forwarded_headers_are_ignored_from_an_untrusted_client(repo, auth, monkeypatch):
    captured = _capture_redirect_uri(monkeypatch)
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    # A client address that is neither loopback nor the TestClient default
    # ("testclient"), with NSIGHT_TRUST_FORWARDED_HEADERS unset: exactly the
    # "backend reachable directly" case _trust_forwarded_headers documents
    # as untrusted, so the forwarded headers below must be ignored even
    # though they're present -- the fallback origin wins instead.
    untrusted = TestClient(app, base_url="https://testserver", client=("203.0.113.5", 12345))
    r = untrusted.get("/auth/login/google", follow_redirects=False,
                      headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "evil.example"})
    assert r.status_code == 302
    assert captured["redirect_uri"] == "https://testserver/auth/callback/google"


def test_forwarded_headers_are_trusted_from_an_untrusted_client_when_the_override_is_set(
        repo, auth, monkeypatch):
    captured = _capture_redirect_uri(monkeypatch)
    monkeypatch.setenv("NSIGHT_TRUST_FORWARDED_HEADERS", "1")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    # Same non-loopback client address as the test above, but this time the
    # operator has explicitly opted in (docker-compose*.yml's case: the
    # backend has no published port of its own, so nginx is the only thing
    # that can ever reach it even though it isn't loopback).
    trusted_by_setting = TestClient(app, base_url="https://testserver", client=("203.0.113.5", 12345))
    r = trusted_by_setting.get("/auth/login/google", follow_redirects=False,
                              headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "nsight.egohive.ai"})
    assert r.status_code == 302
    assert captured["redirect_uri"] == "https://nsight.egohive.ai/auth/callback/google"


class _AsyncResult:
    """Wraps a plain value so `await oidc.begin(...)` works in a test that
    replaces `begin` with a synchronous stub."""
    def __init__(self, value):
        self._value = value
    def __await__(self):
        async def _coro():
            return self._value
        return _coro().__await__()


_TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _ms_multitenant_transport(rsa_key, nonce_box: dict, *, xms_edov=None):
    """Microsoft `organizations` discovery end-to-end: a template `issuer`
    (see oidc.py's module docstring -- confirmed against Microsoft's real
    discovery document) and a token from an arbitrary tenant, proving the
    full HTTP round trip (routes_auth.py -> oidc.py -> identity.py), not
    just oidc.complete() in isolation (see test_oidc.py for that)."""
    jwks = {"keys": [rsa_key.as_dict()]}

    def _token():
        now = int(time.time())
        claims = {"iss": f"{ISSUER}{_TENANT_ID}/v2.0", "aud": CLIENT_ID, "sub": "user-123",
                 "email": "maija@egoiq.com", "tid": _TENANT_ID,
                 "iat": now, "exp": now + 3600, "nonce": nonce_box["nonce"]}
        if xms_edov is not None:
            claims["xms_edov"] = xms_edov
        return joserfc_jwt.encode({"alg": "RS256", "kid": "test-1"}, claims, rsa_key)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": f"{ISSUER}{{tenantid}}/v2.0", "authorization_endpoint": f"{ISSUER}auth",
                "token_endpoint": f"{ISSUER}token", "jwks_uri": f"{ISSUER}jwks"})
        if request.url.path == "/jwks":
            return httpx.Response(200, json=jwks)
        if request.url.path == "/token":
            return httpx.Response(200, json={
                "access_token": "at-1", "token_type": "Bearer", "id_token": _token()})
        return httpx.Response(404)

    return httpx.MockTransport(handler)


class TestMicrosoftMultiTenantSignIn:
    """Task 12c end-to-end: a genuine token from an arbitrary Entra tenant,
    via the `organizations` endpoint, over the real HTTP routes."""

    @pytest.fixture(autouse=True)
    def _configure_microsoft_multitenant(self, repo, auth):
        stored = repo.get_setting(auth, "oidc.json") or {}
        stored["microsoft"] = {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}
        repo.set_setting(auth, "oidc.json", stored)

    def _round_trip(self, client, monkeypatch, rsa_key, *, xms_edov):
        nonce_box = {"nonce": None}
        transport = _ms_multitenant_transport(rsa_key, nonce_box, xms_edov=xms_edov)
        monkeypatch.setattr(oidc, "_MICROSOFT_MULTITENANT_METADATA_URL",
                            f"{ISSUER}.well-known/openid-configuration")
        monkeypatch.setattr(oidc, "_client",
                            lambda config, redirect_uri, _ignored: oidc.AsyncOAuth2Client(
                                config.client_id, config.client_secret, scope=oidc._SCOPE,
                                redirect_uri=redirect_uri, transport=transport))
        login = client.get("/auth/login/microsoft", follow_redirects=False)
        parsed = urlparse(login.headers["location"])
        nonce_box["nonce"] = parse_qs(parsed.query)["nonce"][0]
        state = parse_qs(parsed.query)["state"][0]
        return client.get(f"/auth/callback/microsoft?code=fake-code&state={state}",
                          follow_redirects=False)

    def test_xms_edov_true_lets_an_unknown_email_auto_join(
            self, client, repo, auth, monkeypatch, rsa_key):
        repo.set_setting(auth, "access.json",
                         {"allowed_domains": ["egoiq.com"], "default_grants": []})
        callback = self._round_trip(client, monkeypatch, rsa_key, xms_edov=True)
        assert callback.status_code == 302
        assert client.cookies.get("nsight_session")

        me = client.get("/auth/me")
        assert me.status_code == 200 and me.json()["email"] == "maija@egoiq.com"

    def test_xms_edov_absent_refuses_an_unknown_email_even_on_an_allowed_domain(
            self, client, repo, auth, monkeypatch, rsa_key):
        repo.set_setting(auth, "access.json",
                         {"allowed_domains": ["egoiq.com"], "default_grants": []})
        callback = self._round_trip(client, monkeypatch, rsa_key, xms_edov=None)
        assert callback.status_code == 302
        assert "/login" in callback.headers["location"]
        assert not client.cookies.get("nsight_session")

    def test_xms_edov_absent_still_signs_in_a_known_user(
            self, client, repo, auth, monkeypatch, rsa_key):
        from reportbuilder.auth.permissions import User  # noqa: PLC0415

        repo.save_user(auth, User(id="", email="maija@egoiq.com", name="Maija"))
        callback = self._round_trip(client, monkeypatch, rsa_key, xms_edov=None)
        assert callback.status_code == 302
        assert client.cookies.get("nsight_session")

        me = client.get("/auth/me")
        assert me.status_code == 200 and me.json()["email"] == "maija@egoiq.com"


# ---------------------------------------------------------------------------
# Where sign-in sends you afterwards.
#
# `next` arrived in the query string and was used verbatim as the Location
# header at the end of the flow. A link to OUR sign-in carrying somebody else's
# URL walked the victim through a genuine Google consent screen and dropped
# them on the attacker's page, still believing they were inside nSight — on our
# domain, under our certificate, having just signed in for real.
# ---------------------------------------------------------------------------

def _round_trip(client, monkeypatch, rsa_key, next_param: str) -> str:
    """Sign in for real with this `next`, and return where it sent the browser."""
    monkeypatch.setenv("NSIGHT_BOOTSTRAP_ADMINS", "maija@egoiq.com")
    nonce_box = {"nonce": None}
    transport = _fake_idp_transport(rsa_key, nonce_box)
    monkeypatch.setattr(oidc, "_client",
                        lambda config, redirect_uri, _ignored: oidc.AsyncOAuth2Client(
                            config.client_id, config.client_secret, scope=oidc._SCOPE,
                            redirect_uri=redirect_uri, transport=transport))

    login = client.get(f"/auth/login/google?next={quote(next_param, safe='')}",
                       follow_redirects=False)
    parsed = urlparse(login.headers["location"])
    nonce_box["nonce"] = parse_qs(parsed.query)["nonce"][0]
    state = parse_qs(parsed.query)["state"][0]
    callback = client.get(f"/auth/callback/google?code=fake-code&state={state}",
                          follow_redirects=False)
    assert callback.status_code == 302
    return callback.headers["location"]


def test_sign_in_returns_you_to_the_page_you_came_from(client, monkeypatch, rsa_key):
    assert _round_trip(client, monkeypatch, rsa_key,
                       "/cases/abc123?step=design") == "/cases/abc123?step=design"


@pytest.mark.parametrize("hostile", [
    "https://evil.example/harvest",
    "//evil.example/harvest",          # protocol-relative: another origin
    "/\\evil.example/harvest",         # read as protocol-relative too
    "javascript:alert(1)",
])
def test_it_never_hands_the_browser_to_somebody_else(client, monkeypatch, rsa_key,
                                                     hostile):
    assert _round_trip(client, monkeypatch, rsa_key, hostile) == "/"
