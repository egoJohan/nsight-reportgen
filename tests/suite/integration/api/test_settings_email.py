"""GET/PUT /settings/email -- where the SMTP transport for invitations
(spec §6) is configured."""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext
from suite._helpers import sign_in_override

pytestmark = pytest.mark.integration


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def admin_client(repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth, admin=True)
    return TestClient(app)


@pytest.fixture
def viewer_client(repo, auth):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth, admin=False)
    return TestClient(app)


def test_defaults_to_unconfigured(admin_client):
    r = admin_client.get("/settings/email")
    assert r.status_code == 200
    assert r.json()["configured"] is False


def test_admin_can_set_it(admin_client):
    body = {"host": "smtp.example.com", "port": 2525, "username": "u",
           "password": "s3cr3t", "from_addr": "nsight@example.com", "use_tls": True}
    r = admin_client.put("/settings/email", json=body)
    assert r.status_code == 200
    got = r.json()
    assert got["configured"] is True
    assert "password" not in got  # never echoed back


def test_saving_again_with_no_password_keeps_the_stored_one(admin_client):
    admin_client.put("/settings/email", json={
        "host": "smtp.example.com", "from_addr": "nsight@example.com", "password": "s3cr3t"})
    admin_client.put("/settings/email", json={
        "host": "smtp.example.com", "from_addr": "nsight@example.com", "port": 465})
    assert admin_client.get("/settings/email").json()["configured"] is True


def test_missing_host_is_rejected(admin_client):
    r = admin_client.put("/settings/email", json={"from_addr": "a@b.c"})
    assert r.status_code == 422


def test_a_non_admin_cannot_read_or_write_it(viewer_client):
    assert viewer_client.get("/settings/email").status_code == 403
    assert viewer_client.put("/settings/email", json={}).status_code == 403
