"""Changing your own name, and nobody else's.

The route takes no user id — not in the path, not in the body — so there is no
shape of request that edits somebody else's account. These tests exist to keep
it that way, and to keep the two things it must never touch (`is_admin`,
grants) out of reach of a self-service endpoint.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import Grant, User
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
def me(repo, auth):
    # Named the way `identity.resolve_signed_in_user` names a new account.
    return repo.save_user(auth, User(id="", email="johan.wessberg@egoiq.com",
                                     name="johan.wessberg"))


@pytest.fixture
def client(repo, auth, me):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = lambda: repo.get_user(auth, me.id)
    return TestClient(app)


def test_a_new_account_is_named_from_its_email(client):
    """Better than a blank space where a name should be, and true from the
    moment the account exists."""
    assert client.get("/auth/me").json()["name"] == "johan.wessberg"


def test_setting_a_name_changes_what_the_app_shows(client, repo, auth, me):
    r = client.patch("/auth/me", json={"first_name": "Johan", "last_name": "Wessberg"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Johan Wessberg"
    assert repo.get_user(auth, me.id).first_name == "Johan"


def test_a_first_name_alone_is_enough(client):
    assert client.patch("/auth/me", json={"first_name": "Johan"}).json()["name"] == "Johan"


def test_clearing_both_leaves_no_name(client):
    """Empty, not "johan.wessberg" — every screen that shows a name already
    renders `name || email`, so this is what makes the email reappear. Deriving
    one here instead would pre-empt that fallback everywhere."""
    client.patch("/auth/me", json={"first_name": "Johan", "last_name": "Wessberg"})
    r = client.patch("/auth/me", json={"first_name": "", "last_name": ""})
    assert r.json()["name"] == ""


def test_whitespace_is_not_a_name(client):
    assert client.patch("/auth/me", json={"first_name": "   "}).json()["name"] == ""


def test_it_cannot_make_you_an_admin(client, repo, auth, me):
    """The field is ignored, not refused — but it must not take effect."""
    client.patch("/auth/me", json={"first_name": "Johan", "is_admin": True})
    assert repo.get_user(auth, me.id).is_admin is False


def test_it_cannot_grant_you_anything(client, repo, auth, me):
    client.patch("/auth/me", json={"first_name": "Johan",
                                   "grants": [{"scope": "attendo", "mode": "edit"}]})
    assert repo.get_user(auth, me.id).grants == ()


def test_it_cannot_rename_somebody_else(client, repo, auth):
    """No id is read from anywhere, so naming one changes nothing."""
    other = repo.save_user(auth, User(id="", email="someone@egoiq.com",
                                      grants=(Grant("attendo", "view"),)))
    client.patch("/auth/me", json={"id": other.id, "user_id": other.id,
                                   "email": other.email, "first_name": "Hijacked"})
    assert repo.get_user(auth, other.id).first_name == ""
    assert repo.get_user(auth, other.id).name == ""


def test_an_absurd_name_is_refused(client):
    assert client.patch("/auth/me", json={"first_name": "x" * 101}).status_code == 422


def test_renaming_leaves_grants_and_admin_alone(client, repo, auth):
    admin = repo.save_user(auth, User(id="", email="a@egoiq.com", is_admin=True,
                                      grants=(Grant("attendo", "edit"),)))
    app_repo_user = repo.get_user(auth, admin.id)
    assert app_repo_user.is_admin and app_repo_user.grants
    # rename someone else's account through the store the way the app would
    import dataclasses
    repo.save_user(auth, dataclasses.replace(app_repo_user, first_name="A"))
    after = repo.get_user(auth, admin.id)
    assert after.is_admin is True and after.grants == (Grant("attendo", "edit"),)
