"""An owner can name who reaches their customer, without being an admin.

The permissions dialog used to read `GET /users` and write
`PUT /users/{id}/grants` — both admin-only, and the second one replaces a
person's WHOLE grant list. Handing that to an owner would hand them every
customer in the tenant, so an owner got 403 and an empty dialog: able to close
their customer off, unable to say who stays.

These two routes are the customer-scoped equivalents. They disclose the same
roster an admin already sees, to someone who administers THIS customer, and
they touch exactly one entry in one person's grants. (Johan, 2026-09-14)
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
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth

    def _me():
        stored = repo.get_user(auth, user_id)
        return User(id=user_id, email=email, name=email, is_admin=admin,
                    grants=tuple(stored.grants) if stored else ())

    app.dependency_overrides[current_user] = _me
    return TestClient(app)


@pytest.fixture
def world(repo, auth):
    """An owner who is NOT an admin, a colleague, an admin who owns nothing,
    and a customer with a real owner."""
    owner = repo.save_user(auth, User(id="", email="owner@nsight.fi", name="Owner"))
    mate = repo.save_user(auth, User(id="", email="mate@nsight.fi", name="Mate"))
    boss = repo.save_user(auth, User(id="", email="boss@nsight.fi", name="Boss",
                                     is_admin=True))
    cid = repo.create_customer(auth, "Attendo", owner_id=owner.id).id
    repo.set_grants(auth, owner.id, (Grant(cid, "edit"),))
    return {"owner": owner, "mate": mate, "boss": boss, "cid": cid}


def test_the_owner_can_list_who_reaches_it(repo, auth, world):
    client = client_as(repo, auth, world["owner"].id, world["owner"].email)
    out = client.get(f"/customers/{world['cid']}/access")
    assert out.status_code == 200, out.text
    body = out.json()
    assert [p["email"] for p in body["people"]] == ["owner@nsight.fi"]
    assert body["people"][0]["is_owner"] is True
    assert "mate@nsight.fi" in [c["email"] for c in body["candidates"]]


def test_an_admin_who_does_not_own_it_cannot_even_look(repo, auth, world):
    client = client_as(repo, auth, world["boss"].id, world["boss"].email, admin=True)
    assert client.get(f"/customers/{world['cid']}/access").status_code == 403


def test_the_owner_can_give_somebody_access(repo, auth, world):
    client = client_as(repo, auth, world["owner"].id, world["owner"].email)
    out = client.put(f"/customers/{world['cid']}/access",
                     json={"user_id": world["mate"].id, "mode": "view"})
    assert out.status_code == 200, out.text
    assert [(g.scope, g.mode) for g in repo.get_user(auth, world["mate"].id).grants] \
        == [(world["cid"], "view")]


def test_granting_here_never_touches_another_customer(repo, auth, world):
    """The reason this exists instead of handing an owner the admin route,
    which replaces the whole list."""
    other = repo.create_customer(auth, "Elsewhere").id
    repo.set_grants(auth, world["mate"].id, (Grant(other, "edit"),))
    client = client_as(repo, auth, world["owner"].id, world["owner"].email)

    client.put(f"/customers/{world['cid']}/access",
               json={"user_id": world["mate"].id, "mode": "edit"})

    scopes = {g.scope: g.mode for g in repo.get_user(auth, world["mate"].id).grants}
    assert scopes == {other: "edit", world["cid"]: "edit"}, \
        "the other customer's grant was disturbed"


def test_access_can_be_taken_away_again(repo, auth, world):
    client = client_as(repo, auth, world["owner"].id, world["owner"].email)
    client.put(f"/customers/{world['cid']}/access",
               json={"user_id": world["mate"].id, "mode": "view"})
    client.put(f"/customers/{world['cid']}/access",
               json={"user_id": world["mate"].id, "mode": None})
    assert repo.get_user(auth, world["mate"].id).grants == ()


def test_the_owner_cannot_be_removed_from_their_own_customer(repo, auth, world):
    client = client_as(repo, auth, world["owner"].id, world["owner"].email)
    out = client.put(f"/customers/{world['cid']}/access",
                     json={"user_id": world["owner"].id, "mode": None})
    assert out.status_code == 409, out.text
    assert repo.get_user(auth, world["owner"].id).grants, "the owner lost their own customer"


def test_the_owner_cannot_be_downgraded_to_view(repo, auth, world):
    client = client_as(repo, auth, world["owner"].id, world["owner"].email)
    assert client.put(f"/customers/{world['cid']}/access",
                      json={"user_id": world["owner"].id, "mode": "view"}).status_code == 409


def test_a_colleague_cannot_hand_themselves_access(repo, auth, world):
    client = client_as(repo, auth, world["mate"].id, world["mate"].email)
    assert client.put(f"/customers/{world['cid']}/access",
                      json={"user_id": world["mate"].id, "mode": "edit"}).status_code == 403


def test_an_unknown_person_is_404(repo, auth, world):
    client = client_as(repo, auth, world["owner"].id, world["owner"].email)
    assert client.put(f"/customers/{world['cid']}/access",
                      json={"user_id": "usr-nobody", "mode": "view"}).status_code == 404


def test_an_unknown_mode_is_refused(repo, auth, world):
    client = client_as(repo, auth, world["owner"].id, world["owner"].email)
    assert client.put(f"/customers/{world['cid']}/access",
                      json={"user_id": world["mate"].id, "mode": "owner"}).status_code == 422


def test_an_ownerless_customer_is_an_admins_to_manage(repo, auth, world):
    """Taffel's shape — nobody recorded as owner, so an admin keeps it usable."""
    legacy = repo.create_customer(auth, "Legacy").id
    boss = client_as(repo, auth, world["boss"].id, world["boss"].email, admin=True)
    assert boss.get(f"/customers/{legacy}/access").status_code == 200
    assert boss.put(f"/customers/{legacy}/access",
                    json={"user_id": world["mate"].id, "mode": "view"}).status_code == 200
