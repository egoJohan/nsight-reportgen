"""Guessing a password has to get harder.

`POST /auth/login/password` runs an Argon2 verification on every request. That
expense is the point of Argon2 — and it is also what makes an unlimited
endpoint an amplifier: a few hundred requests a second cost the attacker
nothing and cost this container every core it has. An endpoint that will answer
a password guess for ever is a password guesser's endpoint.

What this must NOT do is lock a real person out of their own account.
"""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api import routes_auth
from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration

GOOD = "correct horse battery staple"
EMAIL = "admin@egoiq.com"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NSIGHT_BOOTSTRAP_ADMINS", EMAIL)
    app = create_app()
    repo = Repository(InMemoryObjectStore())
    auth = AuthContext(token="test")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    c = TestClient(app)
    c.post("/auth/register", json={"email": EMAIL, "password": GOOD})
    c.cookies.clear()
    return c


def _try(client, password):
    return client.post("/auth/login/password",
                       json={"email": EMAIL, "password": password})


def test_guessing_is_eventually_refused(client):
    limit = routes_auth._LOGIN_ATTEMPTS.limit
    for _ in range(limit):
        assert _try(client, "wrong").status_code == 401
    blocked = _try(client, "wrong")
    assert blocked.status_code == 429
    assert "Retry-After" in blocked.headers


def test_the_right_password_still_works_after_a_few_fumbles(client):
    """Two typos must not cost anyone their afternoon."""
    for _ in range(2):
        assert _try(client, "wrong").status_code == 401
    assert _try(client, GOOD).status_code == 200


def test_a_successful_sign_in_clears_what_came_before_it(client):
    """Otherwise a fumble this morning is still being counted this afternoon,
    and the person who mistypes twice a day is barred by lunchtime."""
    limit = routes_auth._LOGIN_ATTEMPTS.limit
    for _ in range(limit - 1):
        assert _try(client, "wrong").status_code == 401
    assert _try(client, GOOD).status_code == 200
    client.cookies.clear()
    for _ in range(limit - 1):
        assert _try(client, "wrong").status_code == 401, "the count started over"


def test_once_blocked_the_right_password_is_refused_too(client):
    """The block is on the caller, not on the guess. Letting a correct password
    through would turn the limit into a way to test one more guess for free."""
    for _ in range(routes_auth._LOGIN_ATTEMPTS.limit):
        _try(client, "wrong")
    assert _try(client, GOOD).status_code == 429


def test_registration_is_counted_as_well(client):
    """It hashes a password and refuses most callers — an amplifier with an
    audience."""
    for _ in range(routes_auth._LOGIN_ATTEMPTS.limit):
        r = client.post("/auth/register",
                        json={"email": "nobody@example.com", "password": GOOD})
        assert r.status_code in (403, 429)
    assert client.post("/auth/register",
                       json={"email": "nobody@example.com",
                             "password": GOOD}).status_code == 429
