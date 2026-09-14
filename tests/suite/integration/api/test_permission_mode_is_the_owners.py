"""Only a customer's owner decides who may reach it.

Being an admin is the right to manage USERS, not a key to a customer's data
(spec §5). If it opened this control too, any admin could switch a customer to
manual and name themselves — which is the one thing the setting exists to
prevent, so the gate is ownership, not the admin flag.

A customer recorded before ownership existed has nobody to ask. Refusing
everybody would leave it permanently unmanageable with no way back through the
UI, so those fall back to an admin: narrow, deliberate, and closed as soon as
such a customer is given an owner.

And switching to manual must never orphan a customer. Measured the hard way on
Johan's local hive: Taffel had no owner, his access came from the `egoiq.com`
domain grant, he switched it to manual, and the switch withdrew the only thing
admitting him. (Johan, 2026-09-14)
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
def auth():
    return AuthContext(token="t")


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


def client_as(repo, auth, user_id, email, *, admin=False):
    """A client acting as one specific person, grants re-read every request so
    a grant written mid-test is seen on the next call."""
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth

    def _me():
        stored = repo.get_user(auth, user_id)
        grants = tuple(stored.grants) if stored else ()
        return User(id=user_id, email=email, name=email, is_admin=admin, grants=grants)

    app.dependency_overrides[current_user] = _me
    return TestClient(app)


def _owned_customer(repo, auth, owner_id, name="Attendo"):
    """A customer with a real owner, as `create_customer` records one — plus
    the explicit edit grant the creation route writes."""
    c = repo.create_customer(auth, name, owner_id=owner_id)
    owner = repo.get_user(auth, owner_id)
    repo.set_grants(auth, owner_id, tuple(owner.grants) + (Grant(c.id, "edit"),))
    return c.id


def test_the_owner_may_switch_it_even_without_being_an_admin(repo, auth):
    owner = repo.save_user(auth, User(id="", email="owner@nsight.fi", name="Owner"))
    cid = _owned_customer(repo, auth, owner.id)
    client = client_as(repo, auth, owner.id, owner.email, admin=False)

    out = client.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})
    assert out.status_code == 200, out.text


def test_an_admin_who_does_not_own_it_is_refused(repo, auth):
    """The escalation this closes: an admin switching a customer to manual and
    naming themselves."""
    owner = repo.save_user(auth, User(id="", email="owner@nsight.fi", name="Owner"))
    admin = repo.save_user(auth, User(id="", email="boss@nsight.fi", name="Boss",
                                      is_admin=True))
    cid = _owned_customer(repo, auth, owner.id)
    client = client_as(repo, auth, admin.id, admin.email, admin=True)

    out = client.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})
    assert out.status_code == 403, out.text


def test_a_plain_stranger_is_refused_too(repo, auth):
    owner = repo.save_user(auth, User(id="", email="owner@nsight.fi", name="Owner"))
    other = repo.save_user(auth, User(id="", email="other@nsight.fi", name="Other"))
    cid = _owned_customer(repo, auth, owner.id)
    client = client_as(repo, auth, other.id, other.email, admin=False)

    assert client.put(f"/customers/{cid}/permission-mode",
                      json={"mode": "manual"}).status_code == 403


def test_a_customer_with_no_owner_falls_back_to_an_admin(repo, auth):
    """Taffel's shape: recorded before ownership was. Somebody has to be able
    to manage it, or it is unmanageable for ever."""
    admin = repo.save_user(auth, User(id="", email="boss@nsight.fi", name="Boss",
                                      is_admin=True))
    cid = repo.create_customer(auth, "Legacy").id
    client = client_as(repo, auth, admin.id, admin.email, admin=True)

    assert client.put(f"/customers/{cid}/permission-mode",
                      json={"mode": "manual"}).status_code == 200


def test_a_non_admin_cannot_manage_an_ownerless_customer(repo, auth):
    plain = repo.save_user(auth, User(id="", email="plain@nsight.fi", name="Plain"))
    cid = repo.create_customer(auth, "Legacy").id
    client = client_as(repo, auth, plain.id, plain.email, admin=False)

    assert client.put(f"/customers/{cid}/permission-mode",
                      json={"mode": "manual"}).status_code == 403


def test_switching_an_ownerless_customer_does_not_lock_the_caller_out(repo, auth):
    """The defect itself. No owner to protect, the caller's access derived from
    the domain, and the switch withdrawing it — the customer must not become
    unreachable by everybody."""
    repo.set_setting(auth, "access.json",
                     {"allowed_domains": [],
                      "domain_access": [{"domain": "nsight.fi", "mode": "edit"}]})
    admin = repo.save_user(auth, User(id="", email="boss@nsight.fi", name="Boss",
                                      is_admin=True))
    cid = repo.create_customer(auth, "Legacy").id      # no owner_id
    client = client_as(repo, auth, admin.id, admin.email, admin=True)
    assert not repo.get_user(auth, admin.id).grants, "starts with nothing of their own"

    out = client.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})
    assert out.status_code == 200, out.text

    kept = [g for g in repo.get_user(auth, admin.id).grants
            if g.scope == cid and g.mode == "edit"]
    assert kept, "the switch left nobody able to reach the customer"


def test_the_owner_is_the_one_kept_when_there_is_one(repo, auth):
    """Not the caller — the owner, whose customer it is."""
    owner = repo.save_user(auth, User(id="", email="owner@nsight.fi", name="Owner"))
    cid = _owned_customer(repo, auth, owner.id)
    client = client_as(repo, auth, owner.id, owner.email, admin=False)

    client.put(f"/customers/{cid}/permission-mode", json={"mode": "manual"})
    kept = [g for g in repo.get_user(auth, owner.id).grants
            if g.scope == cid and g.mode == "edit"]
    assert kept


def test_switching_back_to_inherit_needs_the_same_right(repo, auth):
    """Otherwise a non-owner could re-open a customer the owner closed."""
    owner = repo.save_user(auth, User(id="", email="owner@nsight.fi", name="Owner"))
    admin = repo.save_user(auth, User(id="", email="boss@nsight.fi", name="Boss",
                                      is_admin=True))
    cid = _owned_customer(repo, auth, owner.id)
    client_as(repo, auth, owner.id, owner.email).put(
        f"/customers/{cid}/permission-mode", json={"mode": "manual"})

    intruder = client_as(repo, auth, admin.id, admin.email, admin=True)
    assert intruder.put(f"/customers/{cid}/permission-mode",
                        json={"mode": "inherit"}).status_code == 403
