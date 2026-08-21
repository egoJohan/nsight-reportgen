"""Spec §10's error table, for the OIDC path specifically.

`tests/suite/unit/auth/test_oidc.py` already proves `oidc.complete()`'s own
crypto refusals (forged signature, alg:none, expired, wrong aud/iss, nonce
mismatch, email_verified/xms_edov rules) -- 14 tests, not repeated here.
`tests/suite/integration/api/test_auth_oidc_flow.py` already proves the HTTP
happy path, an unconfigured provider on the LOGIN route (503), a state
"mismatch" against a cookie so mangled it never survives decoding, and a
verified-but-unadmitted email being refused with no session in the client's
cookie jar. What's below is the rest of the table: a provider that never
answers, the callback's state failures NOT already covered (replay, a
genuine mismatch against a validly-signed cookie, expiry, an absent state or
code), an unknown provider name on both routes, a provider removed between
login and callback, a refused sign-in checked at the header level (no
Set-Cookie at all) plus what happens to `next` on that path, and a provider
that reports an error instead of a code (the "user clicked Cancel" case).
"""
import time as time_module
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient
from joserfc import jwk as joserfc_jwk

from reportbuilder.api import routes_auth
from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import oidc, session
from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext
from tests.suite.integration.api.test_auth_oidc_flow import _id_token

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


@pytest.fixture
def client(repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    # https, not the TestClient default http://testserver: both cookies this
    # flow sets (nsight_oauth, nsight_session) are Secure -- same fix as
    # test_auth_oidc_flow.py / test_sign_in_flow.py.
    return TestClient(app, base_url="https://testserver")


def _fake_idp_transport(rsa_key, *, token_response=None):
    """Discovery + JWKS from *rsa_key*; the token endpoint answers with
    *token_response* (a plain dict, optionally with a "status" key to
    override the default 200) if given, else 404 -- callers whose failure
    happens before ever reaching the token endpoint can leave it out."""
    jwks = {"keys": [rsa_key.as_dict()]}
    body = dict(token_response) if token_response is not None else None
    status = body.pop("status", 200) if body is not None else None

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/.well-known/openid-configuration"):
            return httpx.Response(200, json={
                "issuer": ISSUER, "authorization_endpoint": f"{ISSUER}auth",
                "token_endpoint": f"{ISSUER}token", "jwks_uri": f"{ISSUER}jwks"})
        if request.url.path == "/jwks":
            return httpx.Response(200, json=jwks)
        if request.url.path == "/token" and body is not None:
            return httpx.Response(status, json=body)
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def _patch_transport(monkeypatch, transport):
    monkeypatch.setattr(oidc, "_client",
                        lambda config, redirect_uri, _ignored: oidc.AsyncOAuth2Client(
                            config.client_id, config.client_secret, scope=oidc._SCOPE,
                            redirect_uri=redirect_uri, transport=transport))


def _valid_oauth_cookie(repo, auth, *, state="state-1", nonce="nonce-1", next="/"):
    """A genuinely signed nsight_oauth cookie value, built the same way
    routes_auth.oidc_login builds one -- for tests that need a callback
    request carrying a KNOWN-VALID cookie without driving a real
    /auth/login/{provider} round trip first."""
    key = get_or_create_signing_key(repo, auth)
    return routes_auth._oauth_codec(key).dumps({"state": state, "nonce": nonce, "next": next})


def _begin_login(client, monkeypatch, rsa_key):
    """Drives GET /auth/login/google against the fake IdP and returns
    (state, nonce) parsed from the redirect -- the real state/nonce
    routes_auth.oidc_login generated and stashed in the cookie now sitting
    in `client`'s jar, not values a test invented."""
    _patch_transport(monkeypatch, _fake_idp_transport(rsa_key))
    login = client.get("/auth/login/google", follow_redirects=False)
    parsed = urlparse(login.headers["location"])
    qs = parse_qs(parsed.query)
    return qs["state"][0], qs["nonce"][0]


# --- an unreachable provider: the fix this task ships -----------------------

def test_provider_unreachable_is_a_plain_failure_not_a_500(client, repo, auth, monkeypatch):
    """Spec §10: "OIDC provider unreachable" -> sign-in fails with a plain
    message; existing sessions are unaffected (there is none here yet, but
    the response itself must not be a raw 500)."""
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}})

    def _unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, httpx.MockTransport(_unreachable))
    r = client.get("/auth/login/google", follow_redirects=False)
    assert r.status_code in (502, 503)
    assert "500" not in str(r.status_code)


# --- the callback's state handling: what test_auth_oidc_flow.py doesn't ----

def test_a_missing_oauth_cookie_on_callback_is_400_not_500(client):
    r = client.get("/auth/callback/google?code=x&state=y")
    assert r.status_code == 400


def test_a_callback_with_no_state_param_at_all_is_rejected(client, repo, auth):
    """`state` present in the cookie, absent from the query string entirely
    -- distinct from test_auth_oidc_flow.py's mismatch case, which supplies
    a (wrong) state param against a garbage cookie."""
    client.cookies.set(routes_auth._OAUTH_COOKIE, _valid_oauth_cookie(repo, auth))
    r = client.get("/auth/callback/google?code=x")
    assert r.status_code == 400


def test_a_callback_with_no_code_param_at_all_is_rejected_not_500(client, repo, auth):
    client.cookies.set(routes_auth._OAUTH_COOKIE, _valid_oauth_cookie(repo, auth, state="state-1"))
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}})
    lenient = TestClient(client.app, base_url="https://testserver", raise_server_exceptions=False)
    lenient.cookies.set(routes_auth._OAUTH_COOKIE, client.cookies.get(routes_auth._OAUTH_COOKIE))
    r = lenient.get("/auth/callback/google?state=state-1", follow_redirects=False)
    assert r.status_code != 500, f"got {r.status_code}, body={r.text!r}"


def test_a_genuine_state_mismatch_against_a_validly_signed_cookie_is_rejected(client, repo, auth):
    """A validly-signed, unexpired cookie whose *state* simply doesn't match
    the query param -- the actual CSRF-mismatch branch. Not covered by
    test_auth_oidc_flow.py's `test_a_state_mismatch_is_rejected`, which uses
    a cookie so mangled it never survives `_oauth_codec(...).loads` far
    enough to reach the comparison at all."""
    client.cookies.set(routes_auth._OAUTH_COOKIE,
                       _valid_oauth_cookie(repo, auth, state="state-the-cookie-says"))
    r = client.get("/auth/callback/google?code=x&state=state-an-attacker-supplies")
    assert r.status_code == 400


def test_an_expired_oauth_cookie_is_rejected(client, repo, auth):
    """Signed correctly, but older than _OAUTH_MAX_AGE (10 minutes) -- the
    consent screen took too long. itsdangerous embeds the timestamp at
    `dumps()` time via the stdlib `time` module, so it's forged here by
    briefly rewinding `time.time` for the call that mints the cookie, not by
    actually sleeping ten minutes."""
    real_time = time_module.time
    time_module.time = lambda: real_time() - routes_auth._OAUTH_MAX_AGE - 1
    try:
        stale_cookie = _valid_oauth_cookie(repo, auth, state="state-1")
    finally:
        time_module.time = real_time

    client.cookies.set(routes_auth._OAUTH_COOKIE, stale_cookie)
    r = client.get("/auth/callback/google?code=x&state=state-1")
    assert r.status_code == 400


def test_state_replay_is_rejected_after_a_successful_callback(client, repo, auth, monkeypatch, rsa_key):
    """The CSRF defence, proven end to end: a callback URL that already
    succeeded must not work again. The OAuth-state cookie is single-use and
    cleared on every exit path (routes_auth.py's own comment on
    `oidc_callback`), so resending the identical request -- same URL, same
    (now-absent) cookie -- is refused the second time."""
    monkeypatch.setenv("NSIGHT_BOOTSTRAP_ADMINS", "maija@egoiq.com")
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}})

    state, nonce = _begin_login(client, monkeypatch, rsa_key)
    token = _id_token(rsa_key, nonce)
    _patch_transport(monkeypatch, _fake_idp_transport(
        rsa_key, token_response={"access_token": "at-1", "token_type": "Bearer", "id_token": token}))

    url = f"/auth/callback/google?code=fake-code&state={state}"
    first = client.get(url, follow_redirects=False)
    assert first.status_code == 302 and client.cookies.get("nsight_session")
    assert not client.cookies.get(routes_auth._OAUTH_COOKIE)  # cleared already

    replay = client.get(url, follow_redirects=False)  # identical request, resent
    assert replay.status_code == 400


# --- unknown / unconfigured providers ---------------------------------------

def test_an_unknown_provider_name_is_404_on_both_routes(client):
    assert client.get("/auth/login/okta", follow_redirects=False).status_code == 404
    assert client.get("/auth/callback/okta?code=x&state=y").status_code == 404


def test_a_provider_removed_between_login_and_callback_is_503_not_500(client, repo, auth):
    """An operator can un-configure a provider (routes_settings.py) at any
    time -- including the seconds between a user starting a Google sign-in
    and Google redirecting them back. The callback must still fail cleanly:
    a valid, unexpired oauth-state cookie naming "google", but no google
    entry in oidc.json by the time the callback runs (repo has no oidc.json
    at all here -- equivalent to "removed since")."""
    client.cookies.set(routes_auth._OAUTH_COOKIE, _valid_oauth_cookie(repo, auth, state="state-1"))
    r = client.get("/auth/callback/google?code=x&state=state-1", follow_redirects=False)
    assert r.status_code == 503
    assert not client.cookies.get("nsight_session")


# --- a refused sign-in: no session, and what happens to `next` -------------

def test_a_refused_sign_in_mints_no_session_and_sets_no_session_cookie(
        client, repo, auth, monkeypatch, rsa_key):
    """Spec §4 step 3 / §10: a verified email nSight does not admit gets NO
    session -- checked at the header level (no Set-Cookie for nsight_session
    at all), stronger than test_auth_oidc_flow.py's equivalent test, which
    only checks the client's cookie jar afterwards."""
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}})
    state, nonce = _begin_login(client, monkeypatch, rsa_key)
    token = _id_token(rsa_key, nonce)
    _patch_transport(monkeypatch, _fake_idp_transport(
        rsa_key, token_response={"access_token": "at-1", "token_type": "Bearer", "id_token": token}))

    callback = client.get(f"/auth/callback/google?code=fake-code&state={state}",
                          follow_redirects=False)
    assert callback.status_code == 302
    assert "/login?error=not_allowed" in callback.headers["location"]

    set_cookie_headers = callback.headers.get_list("set-cookie")
    assert not any(h.startswith(f"{session.COOKIE_NAME}=") for h in set_cookie_headers)


def test_a_refused_sign_in_drops_the_next_destination(client, repo, auth, monkeypatch, rsa_key):
    """DOCUMENTS a known gap (flagged in Task 13's report, not fixed here --
    the controller decides, per this task's instructions): a refusal always
    redirects to the bare `/login?error=not_allowed`, even when the login
    attempt started with `?next=/somewhere`. `next` correctly survives the
    round trip on the SUCCESS path; this pins that only the REFUSAL path
    loses it. If this starts failing, `next` is being carried through and
    this test -- not the fix -- is what should change."""
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}})
    _patch_transport(monkeypatch, _fake_idp_transport(rsa_key))
    login = client.get("/auth/login/google?next=%2Freports%2F42", follow_redirects=False)
    qs = parse_qs(urlparse(login.headers["location"]).query)
    state, nonce = qs["state"][0], qs["nonce"][0]

    token = _id_token(rsa_key, nonce)
    _patch_transport(monkeypatch, _fake_idp_transport(
        rsa_key, token_response={"access_token": "at-1", "token_type": "Bearer", "id_token": token}))

    callback = client.get(f"/auth/callback/google?code=fake-code&state={state}",
                          follow_redirects=False)
    assert callback.status_code == 302
    assert callback.headers["location"] == "/login?error=not_allowed"
    assert "reports" not in callback.headers["location"]


# --- a provider that comes back with an error instead of a code ------------

def test_a_provider_error_response_does_not_500(client, repo, auth, monkeypatch, rsa_key):
    """The "user clicked Cancel at Google" case: the browser is redirected
    back to `/auth/callback/google?error=access_denied&state=...` -- a real
    `state` (so it passes the CSRF check), but no `code` at all. The route
    doesn't special-case `error`, so it proceeds to a token exchange with an
    empty code; the fake IdP below answers the way a real one does for a
    bad/absent code (400, `{"error": "invalid_grant"}`) rather than
    supplying a working id_token, the way every other fixture in this file
    does. Whatever nSight does with that must not be an unhandled exception
    -- checked here with raise_server_exceptions=False so an uncaught error
    surfaces as a 500 response instead of blowing up the test itself, which
    is the whole point of the assertion."""
    repo.set_setting(auth, "oidc.json",
                     {"google": {"client_id": CLIENT_ID, "client_secret": "s3cr3t"}})
    state, _nonce = _begin_login(client, monkeypatch, rsa_key)

    lenient = TestClient(client.app, base_url="https://testserver", raise_server_exceptions=False)
    lenient.cookies.set(routes_auth._OAUTH_COOKIE, client.cookies.get(routes_auth._OAUTH_COOKIE))

    _patch_transport(monkeypatch, _fake_idp_transport(
        rsa_key, token_response={"status": 400, "error": "invalid_grant",
                                 "error_description": "code was empty"}))

    r = lenient.get(f"/auth/callback/google?error=access_denied&state={state}",
                    follow_redirects=False)
    assert r.status_code != 500, (
        f"a provider error response must land somewhere sane, not a 500 "
        f"(got {r.status_code}, body={r.text!r})")
    assert not lenient.cookies.get("nsight_session")
