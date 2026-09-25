"""A customer whose owner was removed, and giving it a new owner.

"Jos poistaa käyttäjän joka on jonkin asiakkaan owner, ei asiakasta pysty
poistamaan enää" (2026-09-25): the customer kept the removed owner's id, and
only that user could manage it. Now a removed owner counts as none — an admin
acts for the customer — and an admin can give it a new owner, but "only when
the old owner does not exist anymore" (Johan, 2026-09-25).
"""
from __future__ import annotations

import pytest

from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import EDIT, User

pytestmark = pytest.mark.integration


def _repo(client):
    return client.app.dependency_overrides[get_repository](), \
        client.app.dependency_overrides[get_auth]()


def _with_consent(client, method, url, **kw):
    repo, _ = _repo(client)
    for _ in range(200):
        resp = client.request(method, url, **kw)
        detail = resp.json().get("detail") if resp.status_code == 409 else None
        if isinstance(detail, dict) and detail.get("error") == "consent_required":
            repo.store.approve(detail["request_id"])
            continue
        return resp
    raise AssertionError("consent loop did not converge")


def _as(client, user_id):
    repo, auth = _repo(client)
    client.app.dependency_overrides[current_user] = lambda: repo.get_user(auth, user_id)


@pytest.fixture
def world(client_memory):
    """An admin, a colleague, and a customer owned by an owner who is then removed."""
    c = client_memory
    repo, auth = _repo(c)
    admin = repo.save_user(auth, User(id="", email="admin@egoiq.com", name="Admin", is_admin=True))
    colleague = repo.save_user(auth, User(id="", email="maija@egoiq.com", name="Maija"))
    owner = repo.save_user(auth, User(id="", email="owner@egoiq.com", name="Owner"))
    cust = repo.create_customer(auth, "Acme", owner_id=owner.id)
    return {"admin": admin.id, "colleague": colleague.id, "owner": owner.id, "cust": cust.id}


def _remove_owner(c, w):
    repo, auth = _repo(c)
    for _ in range(50):
        try:
            repo.delete_user(auth, w["owner"])
            return
        except Exception as exc:  # noqa: BLE001 — the in-memory consent gate
            repo.store.approve(exc.request_id)


def test_while_the_owner_exists_an_admin_cannot_manage_it(client_memory, world):
    c, w = client_memory, world
    _as(c, w["admin"])
    assert c.get(f"/customers/{w['cust']}/access").status_code == 403
    assert c.delete(f"/customers/{w['cust']}").status_code == 403


def test_once_the_owner_is_removed_an_admin_can_manage_and_delete_it(client_memory, world):
    c, w = client_memory, world
    _remove_owner(c, w)
    _as(c, w["admin"])
    access = c.get(f"/customers/{w['cust']}/access")
    assert access.status_code == 200 and access.json()["owner_id"] is None
    assert _with_consent(c, "DELETE", f"/customers/{w['cust']}").status_code == 200


def test_a_non_admin_still_cannot(client_memory, world):
    c, w = client_memory, world
    _remove_owner(c, w)
    _as(c, w["colleague"])
    assert c.get(f"/customers/{w['cust']}/access").status_code == 403
    assert c.put(f"/customers/{w['cust']}/owner",
                 json={"user_id": w["colleague"]}).status_code == 403


def test_an_admin_gives_an_ownerless_customer_a_new_owner(client_memory, world):
    c, w = client_memory, world
    repo, auth = _repo(c)
    _remove_owner(c, w)
    _as(c, w["admin"])
    r = c.put(f"/customers/{w['cust']}/owner", json={"user_id": w["colleague"]})
    assert r.status_code == 200, r.text
    assert r.json()["owner"] == {"id": w["colleague"], "name": "Maija"}
    assert repo.find_customer(auth, w["cust"]).owner_id == w["colleague"]
    # The new owner can open it and manage it; the admin no longer can.
    assert any(g.scope == w["cust"] and g.mode == EDIT
               for g in repo.get_user(auth, w["colleague"]).grants)
    assert c.get(f"/customers/{w['cust']}/access").status_code == 403
    _as(c, w["colleague"])
    assert c.get(f"/customers/{w['cust']}/access").status_code == 200


def test_never_while_the_owner_exists(client_memory, world):
    c, w = client_memory, world
    _as(c, w["admin"])
    r = c.put(f"/customers/{w['cust']}/owner", json={"user_id": w["admin"]})
    assert r.status_code == 409
    repo, auth = _repo(c)
    assert repo.find_customer(auth, w["cust"]).owner_id == w["owner"]


def test_an_unknown_new_owner_is_404(client_memory, world):
    c, w = client_memory, world
    _remove_owner(c, w)
    _as(c, w["admin"])
    assert c.put(f"/customers/{w['cust']}/owner",
                 json={"user_id": "usr-nope"}).status_code == 404


def test_the_customer_names_its_owner_and_none_once_removed(client_memory, world):
    """The customer page decides from this who sees Manage permissions and
    Delete customer; it used to carry no owner at all."""
    c, w = client_memory, world
    repo, auth = _repo(c)
    from reportbuilder.auth.permissions import Grant
    repo.set_grants(auth, w["colleague"], (Grant(w["cust"], "view"),))
    _as(c, w["colleague"])
    assert c.get(f"/customers/{w['cust']}").json()["owner"] == {"id": w["owner"], "name": "Owner"}
    _remove_owner(c, w)
    assert c.get(f"/customers/{w['cust']}").json()["owner"] is None


def test_an_admin_sees_every_customer_without_an_owner(client_memory, world):
    """Grant or not: an admin with no grant on one could not otherwise find it."""
    c, w = client_memory, world
    repo, auth = _repo(c)
    owned = repo.create_customer(auth, "Owned", owner_id=w["colleague"])
    legacy = repo.create_customer(auth, "Legacy")
    _remove_owner(c, w)
    _as(c, w["admin"])
    listed = c.get("/customers/without-owner")
    assert listed.status_code == 200, listed.text
    ids = {r["id"] for r in listed.json()}
    assert ids == {w["cust"], legacy.id} and owned.id not in ids


def test_only_an_admin_sees_that_list(client_memory, world):
    c, w = client_memory, world
    _as(c, w["colleague"])
    assert c.get("/customers/without-owner").status_code == 403
