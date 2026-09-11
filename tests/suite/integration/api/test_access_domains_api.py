"""The access screen stores two lists: who may sign in, and who is owed what."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.deps import get_auth, get_repository
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.server import create_app
from reportbuilder.auth.permissions import User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext
from suite._helpers import sign_in_override


@pytest.fixture
def auth():
    return AuthContext(token="admin-1")


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


def _client(repo, auth, *, admin: bool):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    if admin:
        app.dependency_overrides[current_user] = sign_in_override(repo, auth, admin=True)
    else:
        app.dependency_overrides[current_user] = lambda: User(
            id="u2", email="viewer@nsight.fi", is_admin=False, grants=())
    return TestClient(app)


@pytest.fixture
def client_admin(repo, auth):
    return _client(repo, auth, admin=True)


@pytest.fixture
def client_plain(repo, auth):
    return _client(repo, auth, admin=False)


def _put(client, payload):
    return client.put("/settings/access", json=payload)


def test_the_two_lists_are_stored_apart(client_admin):
    """Admission and access are separate questions, so they are separate
    fields -- a domain may be in either, both, or neither. (Johan, 2026-09-11)"""
    r = _put(client_admin, {"allowed_domains": ["nsight.fi"],
                            "domain_access": [{"domain": "partner.com", "mode": "view"}],
                            "default_grants": []})
    assert r.status_code == 200, r.text
    got = client_admin.get("/settings/access").json()
    assert got["allowed_domains"] == ["nsight.fi"]
    assert got["domain_access"] == [{"domain": "partner.com", "mode": "view"}]


def test_a_domain_may_be_on_both_lists(client_admin):
    _put(client_admin, {"allowed_domains": ["nsight.fi"],
                        "domain_access": [{"domain": "nsight.fi", "mode": "edit"}],
                        "default_grants": []})
    got = client_admin.get("/settings/access").json()
    assert got["allowed_domains"] == ["nsight.fi"]
    assert got["domain_access"] == [{"domain": "nsight.fi", "mode": "edit"}]


def test_a_settings_file_written_before_the_split_still_reads(client_admin):
    """`domain_access` is simply absent there; the screen must not 500 on it."""
    assert _put(client_admin, {"allowed_domains": [{"domain": "nsight.fi", "mode": "edit"}],
                               "default_grants": []}).status_code == 200
    got = client_admin.get("/settings/access").json()
    assert got["allowed_domains"] == [{"domain": "nsight.fi", "mode": "edit"}]
    assert got["domain_access"] == []


def test_an_access_entry_needs_a_mode_that_exists(client_admin):
    r = _put(client_admin, {"allowed_domains": [],
                            "domain_access": [{"domain": "x.fi", "mode": "owner"}],
                            "default_grants": []})
    assert r.status_code == 422


def test_an_access_entry_needs_a_domain(client_admin):
    r = _put(client_admin, {"allowed_domains": [],
                            "domain_access": [{"mode": "edit"}], "default_grants": []})
    assert r.status_code == 422


def test_access_must_be_a_list(client_admin):
    r = _put(client_admin, {"allowed_domains": [], "domain_access": {},
                            "default_grants": []})
    assert r.status_code == 422


def test_a_domain_can_be_saved_with_a_mode(client_admin):
    r = _put(client_admin, {"allowed_domains": [{"domain": "nsight.fi", "mode": "edit"}],
                            "default_grants": []})
    assert r.status_code == 200
    got = client_admin.get("/settings/access").json()
    assert got["allowed_domains"] == [{"domain": "nsight.fi", "mode": "edit"}]


def test_the_old_bare_string_shape_is_still_accepted(client_admin):
    """Existing settings must keep loading and saving."""
    assert _put(client_admin, {"allowed_domains": ["nsight.fi"],
                               "default_grants": []}).status_code == 200


def test_a_bad_mode_is_refused_rather_than_silently_downgraded(client_admin):
    r = _put(client_admin, {"allowed_domains": [{"domain": "x.fi", "mode": "owner"}],
                            "default_grants": []})
    assert r.status_code == 422


def test_a_domain_without_a_name_is_refused(client_admin):
    r = _put(client_admin, {"allowed_domains": [{"mode": "edit"}], "default_grants": []})
    assert r.status_code == 422


def test_only_an_admin_may_change_it(client_plain):
    """This is who may reach the whole tenant — not ordinary settings."""
    r = _put(client_plain, {"allowed_domains": [{"domain": "x.fi", "mode": "edit"}],
                            "default_grants": []})
    assert r.status_code in (401, 403)
