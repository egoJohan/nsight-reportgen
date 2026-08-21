"""GET/PUT /settings/workspace -- per-user UI state moved out of
localStorage (spec §8)."""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.integration


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def client(repo, auth):
    u = repo.save_user(auth, User(id="", email="a@x.c"))
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = lambda: u
    return TestClient(app)


def test_defaults_to_empty(client):
    assert client.get("/settings/workspace").json() == {}


def test_a_case_can_be_set_and_read_back(client):
    r = client.put("/settings/workspace/case-a", json={"materialId": "mat-1", "reports": []})
    assert r.status_code == 200
    assert client.get("/settings/workspace").json() == {
        "case-a": {"materialId": "mat-1", "reports": []}}


def test_a_second_user_does_not_see_the_firsts_workspace(repo, auth):
    ua = repo.save_user(auth, User(id="", email="a@x.c"))
    ub = repo.save_user(auth, User(id="", email="b@x.c"))
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth

    app.dependency_overrides[current_user] = lambda: ua
    TestClient(app).put("/settings/workspace/case-a", json={"materialId": "mat-1", "reports": []})

    app.dependency_overrides[current_user] = lambda: ub
    assert TestClient(app).get("/settings/workspace").json() == {}
