"""GET/PUT /settings/access -- where domain auto-join is configured."""
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


def test_defaults_to_empty(admin_client):
    r = admin_client.get("/settings/access")
    assert r.status_code == 200
    assert r.json() == {"allowed_domains": [], "default_grants": []}


def test_admin_can_set_it(admin_client):
    body = {"allowed_domains": ["egoiq.com"],
           "default_grants": [{"scope": "attendo", "mode": "view"}]}
    r = admin_client.put("/settings/access", json=body)
    assert r.status_code == 200
    assert admin_client.get("/settings/access").json() == body


def test_a_non_admin_cannot_set_it(viewer_client):
    assert viewer_client.put("/settings/access", json={"allowed_domains": []}).status_code == 403


def test_an_invalid_mode_is_rejected(admin_client):
    body = {"allowed_domains": ["egoiq.com"],
           "default_grants": [{"scope": "attendo", "mode": "delete"}]}
    assert admin_client.put("/settings/access", json=body).status_code == 422
