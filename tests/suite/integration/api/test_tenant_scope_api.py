"""What a whole-tenant domain grant looks like from a request's point of view.

The unit tests cover the rule; these cover the seams a rule can pass while a
screen still shows nothing -- `/auth/me`'s `is_owner`, and a rename writing
the derived grant onto the account. (Johan, 2026-09-10)
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.deps import get_auth, get_repository
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.server import create_app
from reportbuilder.auth.identity import effective_user
from reportbuilder.auth.permissions import EDIT, User
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def maija(repo, auth):
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": [{"domain": "nsight.fi", "mode": EDIT}]})
    return repo.save_user(auth, User(id="", email="maija@nsight.fi", name="Maija"))


@pytest.fixture
def client(repo, auth, maija):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    # Exactly what `session.resolve` hands a request.
    app.dependency_overrides[current_user] = \
        lambda: effective_user(repo, auth, repo.get_user(auth, maija.id))
    return TestClient(app)


def test_a_tenant_editor_reads_as_an_owner(client):
    """`is_owner` is what SettingsPage uses to show the Permission requests
    tab, and the server already serves that queue to anyone holding `edit`.
    Working the flag out from the account's own grants alone left the two
    disagreeing: the route answered, the tab was never drawn."""
    me = client.get("/auth/me").json()
    assert me["is_owner"] is True


def test_a_tenant_editor_sees_a_customer_they_were_never_granted(client, repo, auth):
    made = client.post("/customers", json={"name": "Attendo"})
    assert made.status_code in (200, 201), made.text
    names = [c["name"] for c in client.get("/customers").json()]
    assert "Attendo" in names


def test_renaming_yourself_keeps_you_an_owner_and_writes_no_grant(client, repo, auth, maija):
    out = client.patch("/auth/me", json={"first_name": "Maija", "last_name": "M"})
    assert out.status_code == 200, out.text
    assert out.json()["is_owner"] is True, "the reply must not drop the tenant grant"
    assert repo.get_user(auth, maija.id).grants == (), \
        "a derived grant must never be written onto the account"


def test_saving_the_domains_takes_effect_at_once(repo, auth, maija):
    """Identity is cached for 30 s, so without an eviction an admin sets a
    domain to `edit`, is told it is saved, and the colleague still sees
    nothing for half a minute -- the same trap `PUT /users/{id}/grants`
    already avoids by calling `session.forget_user`. Here the change is
    tenant-wide, so every cached identity is stale at once."""
    from reportbuilder.auth import session as _session

    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = \
        lambda: User(id="a", email="admin@nsight.fi", is_admin=True)
    admin = TestClient(app)

    _session._cache = _session._Cache()
    sid = _session.create(repo, auth, maija.id)
    assert _session.resolve(repo, auth, sid).tenant_grants  # cached, holds edit
    try:
        out = admin.put("/settings/access",
                        json={"allowed_domains": [], "default_grants": []})
        assert out.status_code == 200, out.text
        assert _session.resolve(repo, auth, sid).tenant_grants == ()
    finally:
        _session._cache = _session._Cache()
