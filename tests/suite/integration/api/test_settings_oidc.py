"""GET/PUT /settings/oidc -- where Google/Microsoft client credentials live
(spec §9). No Settings UI reads this yet; an operator sets it directly."""
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
def admin_client():
    app = create_app()
    repo = Repository(InMemoryObjectStore())
    auth = AuthContext(token="t")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth, admin=True)
    return TestClient(app)


def test_defaults_to_unconfigured(admin_client):
    r = admin_client.get("/settings/oidc")
    assert r.json() == {"google": {"configured": False}, "microsoft": {"configured": False}}


def test_setting_google_marks_it_configured_without_echoing_the_secret(admin_client):
    admin_client.put("/settings/oidc", json={
        "google": {"client_id": "abc.apps.googleusercontent.com", "client_secret": "shh"}})
    r = admin_client.get("/settings/oidc")
    assert r.json()["google"] == {"configured": True}
    assert "shh" not in r.text


def test_an_unknown_provider_key_is_rejected(admin_client):
    r = admin_client.put("/settings/oidc", json={"okta": {"client_id": "x", "client_secret": "y"}})
    assert r.status_code == 422


def test_a_non_admin_cannot_read_it(admin_client, monkeypatch):
    # A viewer override, same app.
    from reportbuilder.auth.permissions import User
    admin_client.app.dependency_overrides[current_user] = lambda: User(
        id="v", email="v@x.c", is_admin=False)
    assert admin_client.get("/settings/oidc").status_code == 403
