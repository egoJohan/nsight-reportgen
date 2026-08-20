"""POST /auth/register, /auth/login/password, /auth/logout, GET /auth/me."""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("NSIGHT_BOOTSTRAP_ADMINS", "admin@egoiq.com")
    app = create_app()
    repo = Repository(InMemoryObjectStore())
    auth = AuthContext(token="test")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    return TestClient(app)


def test_the_first_bootstrap_admin_can_register(client):
    r = client.post("/auth/register", json={"email": "admin@egoiq.com",
                                            "password": "correct horse battery staple"})
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "admin@egoiq.com"
    assert r.json()["is_admin"] is True
    assert client.cookies.get("nsight_session")


def test_an_unlisted_email_cannot_register(client):
    r = client.post("/auth/register", json={"email": "nobody@example.com",
                                            "password": "correct horse battery staple"})
    assert r.status_code == 403


def test_a_short_password_is_rejected(client):
    r = client.post("/auth/register", json={"email": "admin@egoiq.com", "password": "short"})
    assert r.status_code == 422


def test_registering_twice_is_refused(client):
    body = {"email": "admin@egoiq.com", "password": "correct horse battery staple"}
    client.post("/auth/register", json=body)
    r = client.post("/auth/register", json=body)
    assert r.status_code == 409


def test_login_with_the_right_password_sets_a_cookie(client):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    client.cookies.clear()
    r = client.post("/auth/login/password",
                    json={"email": "admin@egoiq.com", "password": "correct horse battery staple"})
    assert r.status_code == 200
    assert client.cookies.get("nsight_session")


def test_login_with_the_wrong_password_is_401(client):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    client.cookies.clear()
    r = client.post("/auth/login/password",
                    json={"email": "admin@egoiq.com", "password": "wrong entirely"})
    assert r.status_code == 401
    assert not client.cookies.get("nsight_session")


def test_login_with_an_unknown_email_is_401_not_404(client):
    """Never confirm or deny an account exists (same principle as spec §5's
    "absent, not forbidden" for data)."""
    r = client.post("/auth/login/password",
                    json={"email": "ghost@egoiq.com", "password": "whatever entirely"})
    assert r.status_code == 401


def test_logout_clears_the_cookie(client):
    client.post("/auth/register", json={"email": "admin@egoiq.com",
                                        "password": "correct horse battery staple"})
    r = client.post("/auth/logout")
    assert r.status_code == 200
    assert not client.cookies.get("nsight_session")


def test_logout_with_no_cookie_is_still_200(client):
    assert client.post("/auth/logout").status_code == 200


def test_auth_me_is_public_routes_free_of_it():
    """Sanity check on the census fixture, not the route itself — see
    test_route_census.py for the real assertion."""
    from reportbuilder.api.deps_auth import PUBLIC_ROUTES
    assert "/auth/me" not in PUBLIC_ROUTES
    assert {"/auth/register", "/auth/login/password", "/auth/logout"} <= PUBLIC_ROUTES
