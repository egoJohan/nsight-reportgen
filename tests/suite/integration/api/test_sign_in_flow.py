"""The whole password path, over HTTP: register (gated), log in, act, sign
out, and the two clocks (idle timeout, absolute lifetime) that end a session
without a sign-out (spec §4, §7).

Beyond the required happy/sad paths, this file covers what a real deployment
does that a happy-path test does not: the absolute-lifetime clock as distinct
from idle, concurrent sessions for one user, a user deleted or re-granted out
from under a live cookie, the /auth/me response shape, sign-out's
idempotency, and the two branches of /auth/register a duplicate-email test
alone does not reach (an existing account WITH a password vs one without).
"""
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import identity, session
from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.auth.permissions import Grant
from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired

pytestmark = pytest.mark.integration


def approve_all(store, fn):
    """Run *fn*, approving each consent request until it completes.

    `InMemoryObjectStore` gates every first delete behind a consent request,
    unconditionally. `repo.delete_user` — unlike `repo.delete_session` —
    does NOT swallow that gate, so a test that needs a user ACTUALLY gone
    (not just their session) has to drive it to completion, same as
    `tests/suite/unit/auth/test_session.py`.
    """
    for _ in range(50):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


@pytest.fixture(autouse=True)
def _reset_session_cache():
    """`session._cache` is module-level and shared across the whole process.
    Several tests below assert on its timing precisely (mid-session grant
    changes, a deleted user surviving until the cache expires), so a leftover
    entry from another test must not be able to answer for this one."""
    session._cache = session._Cache()
    yield
    session._cache = session._Cache()


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="test")


@pytest.fixture
def client(repo, auth, monkeypatch):
    monkeypatch.setenv("NSIGHT_BOOTSTRAP_ADMINS", "admin@egoiq.com")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    # https, not the default http://testserver: the session cookie is Secure
    # (routes_auth._issue_session), so plain http would store it but never
    # send it back — see test_current_user_session.py.
    return TestClient(app, base_url="https://testserver")


def _only_session_id(repo, auth) -> str:
    [only] = [s for s in repo.store.list(auth, "settings/", labels=["nsight:session"])]
    return only.path.rsplit("/", 1)[-1]


def _session_ids(repo, auth) -> list[str]:
    return [s.path.rsplit("/", 1)[-1]
           for s in repo.store.list(auth, "settings/", labels=["nsight:session"])]


# --- the required path: register, act, sign out, the two clocks -----------

def test_bootstrap_admin_signs_up_signs_in_acts_and_signs_out(client):
    r = client.post("/auth/register", json={"email": "admin@egoiq.com",
                                            "password": "correct horse battery staple"})
    assert r.status_code == 201 and r.json()["is_admin"] is True

    # An admin with no grants sees no customers (Plan 1, spec §5) — the
    # session is real; the permission model is untouched by this plan.
    assert client.get("/customers").json() == []

    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_domain_auto_join_gives_default_grants_immediately(client, repo, auth):
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": ["egoiq.com"],
                      "default_grants": [{"scope": "attendo", "mode": "edit"}]})
    r = client.post("/auth/register", json={"email": "colleague@egoiq.com",
                                            "password": "correct horse battery staple"})
    assert r.status_code == 201 and r.json()["is_admin"] is False

    c = client.post("/customers", json={"name": "Attendo"})
    # Not literally "attendo" unless the repo happens to id it that way — the
    # point is the grant reaches SOME customer without an admin's help.
    assert c.status_code == 201


def test_a_revoked_session_stops_working_on_the_next_request(client, repo, auth):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    assert client.get("/auth/me").status_code == 200

    # Revoke the ONE session that exists, bypassing the cookie entirely — this
    # is what an admin's "sign this person out" acts on (Plan 3's UI; the
    # primitive is Task 1's delete_sessions_for_user).
    session_id = _only_session_id(repo, auth)
    session.revoke(repo, auth, session_id)

    assert client.get("/auth/me").status_code == 401


def test_idle_timeout_ends_a_session_without_a_sign_out(client, repo, auth):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    session_id = _only_session_id(repo, auth)
    long_idle = (datetime.now(timezone.utc)
                - timedelta(seconds=session.IDLE_TIMEOUT_SECONDS + 1)).isoformat(timespec="seconds")
    repo.touch_session(auth, session_id, long_idle)

    assert client.get("/auth/me").status_code == 401


def test_a_session_within_the_revocation_cache_window_is_not_yet_dead(client, repo, auth):
    """Documents spec §7's stated cost, rather than asserting a bug: revoking
    through the STORE directly (not through session.revoke, which also evicts
    this process's cache) can leave a resolve serving the cached User for up
    to CACHE_TTL_SECONDS. Deleting the record is what a second process, or a
    restart, would see immediately; this process's cache is what §7 says
    costs up to 30s."""
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    assert client.get("/auth/me").status_code == 200  # warms this process's cache

    session_id = _only_session_id(repo, auth)
    repo.delete_session(auth, session_id)  # NOT session.revoke — no cache eviction

    assert client.get("/auth/me").status_code == 200  # still cached


# --- the absolute lifetime, as a clock distinct from idle ------------------

def test_the_absolute_lifetime_ends_a_session_that_was_just_active(client, repo, auth):
    """Idle timeout and absolute lifetime are different fields, checked
    independently by `session._expired` — a session with a fresh `last_seen`
    (idle timeout nowhere close) must still die once `expires` is in the
    past. Writes the record directly, the way
    tests/suite/unit/auth/test_session.py's TestExpiry does, because there
    is no HTTP surface for backdating a session's creation."""
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    session_id = _only_session_id(repo, auth)
    live = repo.get_session(auth, session_id)
    expired = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds")
    repo._write_json(auth, P.session_path(session_id),
                     {"id": live.id, "user_id": live.user_id, "created": live.created,
                      "last_seen": live.last_seen,  # fresh: idle would NOT catch this
                      "expires": expired},
                     [P.LABEL_SESSION])

    assert client.get("/auth/me").status_code == 401


# --- signing in twice: two live sessions, not one replacing the other ------

def test_signing_in_twice_creates_two_independent_live_sessions(client, repo, auth):
    """Nothing in create_session/session.create invalidates a caller's other
    sessions — pinning that deliberately, since either behaviour (coexist or
    replace) would be a defensible design and only one is what's built."""
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    second = TestClient(client.app, base_url="https://testserver")
    r = second.post("/auth/login/password",
                    json={"email": "admin@egoiq.com",
                          "password": "correct horse battery staple"})
    assert r.status_code == 200

    assert len(_session_ids(repo, auth)) == 2
    assert client.get("/auth/me").status_code == 200
    assert second.get("/auth/me").status_code == 200


def test_revoking_one_concurrent_session_leaves_the_other_alone(client, repo, auth):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    second = TestClient(client.app, base_url="https://testserver")
    second.post("/auth/login/password",
               json={"email": "admin@egoiq.com",
                     "password": "correct horse battery staple"})

    key = get_or_create_signing_key(repo, auth)
    first_raw = client.cookies.get(session.COOKIE_NAME)
    first_session_id = session.session_id_from_cookie(key, first_raw)
    session.revoke(repo, auth, first_session_id)

    assert client.get("/auth/me").status_code == 401
    assert second.get("/auth/me").status_code == 200


# --- a user whose grants change mid-session ---------------------------------

def test_a_grant_added_mid_session_is_stale_until_the_cache_expires(client, repo, auth):
    admin = client.post("/auth/register", json={"email": "admin@egoiq.com",
                                                 "password": "correct horse battery staple"}).json()
    cid = client.post("/customers", json={"name": "Attendo"}).json()["id"]

    repo.set_setting(auth, "access.json",
                     {"allowed_domains": ["egoiq.com"], "default_grants": []})
    colleague = TestClient(client.app, base_url="https://testserver")
    colleague.post("/auth/register", json={"email": "colleague@egoiq.com",
                                           "password": "correct horse battery staple"})
    assert colleague.get("/customers").json() == []  # warms the cache: no grants yet

    colleague_user = repo.find_user_by_email(auth, "colleague@egoiq.com")
    repo.set_grants(auth, colleague_user.id, (Grant(cid, "view"),))

    # Still within CACHE_TTL_SECONDS: the cached User (with no grants) answers.
    assert colleague.get("/customers").json() == []

    real_monotonic = time.monotonic
    try:
        time.monotonic = lambda: real_monotonic() + session.CACHE_TTL_SECONDS + 1
        names = [c["name"] for c in colleague.get("/customers").json()]
        assert names == ["Attendo"]
    finally:
        time.monotonic = real_monotonic


# --- a revoked/deleted user still holding a technically-valid cookie -------

def test_a_deleted_user_eventually_loses_a_cookie_still_signed_correctly(client, repo, auth):
    """The session record survives its user by design (session.resolve's own
    comment: "the session outlives them by at most one resolution"). Within
    the cache window that resolution hasn't happened yet, so the stale cached
    User still answers — after it, the store is consulted again, finds no
    user, and 401s."""
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    assert client.get("/auth/me").status_code == 200  # warms the cache

    admin = repo.find_user_by_email(auth, "admin@egoiq.com")
    approve_all(repo.store, lambda: repo.delete_user(auth, admin.id))

    assert client.get("/auth/me").status_code == 200  # still cached

    real_monotonic = time.monotonic
    try:
        time.monotonic = lambda: real_monotonic() + session.CACHE_TTL_SECONDS + 1
        assert client.get("/auth/me").status_code == 401
    finally:
        time.monotonic = real_monotonic


# --- sign-out: idempotent under a repeated, still-present cookie -----------

def test_sign_out_twice_with_the_same_cookie_is_200_both_times(client):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    raw = client.cookies.get(session.COOKIE_NAME)

    assert client.post("/auth/logout").status_code == 200
    # The server's response cleared the client's jar — reinstate the same
    # (now-dead) cookie to prove the SERVER treats a second sign-out on it as
    # a no-op, not an error, rather than merely proving the client forgot it.
    client.cookies.set(session.COOKIE_NAME, raw)
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_sign_out_with_no_session_at_all_is_200(client):
    assert client.post("/auth/logout").status_code == 200


# --- /auth/me: shape, and no cross-user leakage -----------------------------

def test_me_shape_carries_no_grants_or_password_fields(client):
    r = client.post("/auth/register", json={"email": "admin@egoiq.com",
                                            "password": "correct horse battery staple"})
    body = r.json()
    # is_owner is a boolean SYNTHESISED from the grants (holds edit on at
    # least one customer) -- it is what let this survive the "no grants"
    # rule: the raw grants list still never leaves this route, only the one
    # bit SettingsPage.tsx needs (see routes_auth._user_out).
    assert set(body) == {"id", "email", "name", "is_admin", "is_owner"}

    me = client.get("/auth/me").json()
    assert set(me) == {"id", "email", "name", "is_admin", "is_owner"}
    assert me == body


def test_me_only_ever_answers_for_the_calling_users_own_session(client, repo, auth):
    admin = client.post("/auth/register", json={"email": "admin@egoiq.com",
                                                 "password": "correct horse battery staple"}).json()

    repo.set_setting(auth, "access.json",
                     {"allowed_domains": ["egoiq.com"], "default_grants": []})
    colleague_client = TestClient(client.app, base_url="https://testserver")
    colleague = colleague_client.post(
        "/auth/register",
        json={"email": "colleague@egoiq.com", "password": "correct horse battery staple"},
    ).json()

    assert admin["id"] != colleague["id"]
    assert client.get("/auth/me").json()["email"] == "admin@egoiq.com"
    assert colleague_client.get("/auth/me").json()["email"] == "colleague@egoiq.com"


# --- /auth/register: the branch a same-account duplicate does not reach ----

def test_registering_an_existing_passwordless_account_cannot_take_it_over(client, repo, auth):
    """An account that exists but has never had a password — the shape a
    first Google/O365 sign-in will leave behind once Part B lands. Simulated
    directly through identity.resolve_signed_in_user since there is no OIDC
    entry point yet. Distinct from test_auth_password.py's
    test_registering_twice_is_refused, which covers an account that already
    HAS a password; this is the other branch of the same `if` in
    routes_auth.register -- and the one that used to attach a caller-chosen
    password to a stranger's account (the account-takeover vulnerability
    this test now guards against instead of encoding)."""
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": ["egoiq.com"], "default_grants": []})
    existing = identity.resolve_signed_in_user(repo, auth, "colleague@egoiq.com", frozenset())
    assert repo.get_password_hash(auth, existing.id) is None  # sanity: no password yet

    r = client.post("/auth/register", json={"email": "colleague@egoiq.com",
                                            "password": "correct horse battery staple"})

    assert r.status_code == 403
    assert repo.get_password_hash(auth, existing.id) is None  # still no password
    assert len(repo.list_users(auth)) == 1  # no second account either
    assert not r.cookies.get(session.COOKIE_NAME)  # no session for the caller

    assert client.get("/auth/me").status_code == 401


def test_registering_someone_elses_email_does_not_reach_their_grants(client, repo, auth):
    """The attack this whole fix exists for, reproduced end to end: a victim
    exists passwordlessly via domain auto-join (exactly what nSight creates
    today, and what an OIDC sign-in will create once Part B lands) and
    already holds a grant on a real customer, "Attendo". Before the fix, an
    unauthenticated attacker who merely knew the victim's email address could
    POST it to /auth/register with a password of their own choosing, get
    back a 201 and a session cookie, and then GET /customers and see
    ['Attendo'] -- the victim's grant, inherited. After the fix the attacker
    must come away with nothing: no session, no view of the victim's
    customer, and the victim's account must be untouched."""
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": ["egoiq.com"], "default_grants": []})
    victim = identity.resolve_signed_in_user(repo, auth, "maija@egoiq.com", frozenset())
    assert repo.get_password_hash(auth, victim.id) is None  # sanity: passwordless, as auto-join leaves it

    attendo = repo.create_customer(auth, "Attendo")
    repo.set_grants(auth, victim.id, (Grant(attendo.id, "view"),))

    attacker = TestClient(client.app, base_url="https://testserver")
    r = attacker.post("/auth/register", json={"email": "maija@egoiq.com",
                                              "password": "attacker-chosen-pw"})

    assert r.status_code == 403
    assert not attacker.cookies.get(session.COOKIE_NAME)  # attacker gets no session

    assert attacker.get("/customers").status_code == 401  # and no way to see the victim's grants
    assert repo.get_password_hash(auth, victim.id) is None  # victim's account is untouched
