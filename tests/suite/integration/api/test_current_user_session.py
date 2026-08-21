"""current_user resolves the session cookie. No fallback: this is the seam
Plan 1 built and this plan turns (spec §4, §7)."""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth import session as _session
from reportbuilder.auth.keys import get_or_create_signing_key
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="test")


@pytest.fixture
def client(monkeypatch, repo, auth):
    monkeypatch.delenv("NSIGHT_DEV_USER", raising=False)
    monkeypatch.setenv("NSIGHT_BOOTSTRAP_ADMINS", "admin@egoiq.com")
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    # https, not the default http://testserver: the session cookie is Secure
    # (routes_auth._issue_session), so a plain-http TestClient would store it
    # but never actually send it back on the next request — a test-harness
    # quirk that would silently make every round-trip test below pass for the
    # wrong reason (or fail for a reason unrelated to current_user).
    return TestClient(app, base_url="https://testserver")


def test_no_cookie_is_401(client):
    assert client.get("/customers").status_code == 401


def test_a_garbage_cookie_is_401(client):
    """A cookie whose signature does not verify at all."""
    client.cookies.set("nsight_session", "not-a-real-cookie")
    assert client.get("/customers").status_code == 401


def test_a_forged_cookie_signed_with_the_wrong_key_is_401(client, repo, auth):
    """A well-FORMED cookie, correctly signed, but with a key the server never
    issued — the shape a forgery would actually take, as opposed to plain
    garbage bytes (test_a_garbage_cookie_is_401)."""
    wrong_key = b"\x00" * 32
    forged = _session.cookie_value(wrong_key, "sess-whatever")
    client.cookies.set("nsight_session", forged)
    assert client.get("/customers").status_code == 401


def test_a_validly_signed_cookie_for_a_nonexistent_session_is_401(client, repo, auth):
    """The signature checks out — it really was minted with the server's own
    key — but no session record with this id has ever existed. Distinct from
    both a garbage cookie (signature fails) and an expired/revoked one (a
    record existed once): this is `session.resolve` returning None because
    `repo.get_session` finds nothing at all."""
    key = get_or_create_signing_key(repo, auth)
    cookie = _session.cookie_value(key, "sess-never-issued")
    client.cookies.set("nsight_session", cookie)
    assert client.get("/customers").status_code == 401


def test_a_registered_users_cookie_reaches_me(client):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    r = client.get("/auth/me")
    assert r.status_code == 200 and r.json()["email"] == "admin@egoiq.com"


def test_after_logout_the_cookie_no_longer_works(client):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401


def test_nsight_dev_user_no_longer_does_anything(client, monkeypatch):
    """The env var is gone as a concept, not merely unset by default —
    setting it must not resurrect the old bypass."""
    monkeypatch.setenv("NSIGHT_DEV_USER", "admin@egoiq.com")
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    client.cookies.clear()
    assert client.get("/customers").status_code == 401
