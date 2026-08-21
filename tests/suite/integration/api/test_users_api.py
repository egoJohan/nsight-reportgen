# tests/suite/integration/api/test_users_api.py
"""GET/PUT/PATCH/DELETE /users, POST /users/invite, GET/DELETE /invites --
the Users screen's HTTP surface (spec §5, §6)."""
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.api.deps_auth import current_user
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import Grant, User
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


class TestListUsers:
    def test_lists_every_user_with_grant_names(self, admin_client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        repo.save_user(auth, User(id="", email="a@x.c", grants=(Grant(cid, "edit"),)))
        rows = admin_client.get("/users").json()
        row = next(r for r in rows if r["email"] == "a@x.c")
        assert row["grants"] == [{"scope": cid, "mode": "edit",
                                  "customer_name": "Attendo", "case_name": None}]

    def test_a_non_admin_cannot_list_users(self, viewer_client):
        assert viewer_client.get("/users").status_code == 403


class TestGrants:
    def test_admin_replaces_a_users_grants(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        r = admin_client.put(f"/users/{u.id}/grants",
                             json={"grants": [{"scope": "attendo", "mode": "view"}]})
        assert r.status_code == 200
        assert repo.get_user(auth, u.id).grants == (Grant("attendo", "view"),)

    def test_an_invalid_mode_is_rejected(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        r = admin_client.put(f"/users/{u.id}/grants",
                             json={"grants": [{"scope": "attendo", "mode": "delete"}]})
        assert r.status_code == 422

    def test_an_unknown_user_is_404(self, admin_client):
        assert admin_client.put("/users/usr-nope/grants", json={"grants": []}).status_code == 404


class TestAdminToggle:
    def test_promotes_a_user(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        r = admin_client.patch(f"/users/{u.id}", json={"is_admin": True})
        assert r.status_code == 200 and r.json()["is_admin"] is True

    def test_refuses_to_demote_the_last_admin(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="only@x.c", is_admin=True))
        r = admin_client.patch(f"/users/{u.id}", json={"is_admin": False})
        assert r.status_code == 409
        assert repo.get_user(auth, u.id).is_admin is True


def _delete_approving_consent(client, repo, path: str):
    """DELETE *path*, approving datahive's consent gate (InMemoryObjectStore
    raises it, unconditionally, on a path's first delete -- see
    memory_objects.py) and retrying until it actually goes through. Mirrors
    test_settings_fonts.py's `test_deleting_after_approval_removes_it_everywhere`.
    """
    resp = None
    for _ in range(10):
        resp = client.delete(path)
        if resp.status_code != 409:
            return resp
        detail = resp.json().get("detail")
        if not isinstance(detail, dict) or detail.get("error") != "consent_required":
            return resp
        repo.store.approve(detail["request_id"])
    return resp


class TestRemoveUser:
    def test_removes_an_ordinary_user(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        r = _delete_approving_consent(admin_client, repo, f"/users/{u.id}")
        assert r.status_code == 204
        assert repo.get_user(auth, u.id) is None

    def test_refuses_to_remove_the_last_admin(self, admin_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="only@x.c", is_admin=True))
        r = admin_client.delete(f"/users/{u.id}")
        assert r.status_code == 409
        assert repo.get_user(auth, u.id) is not None

    def test_removing_an_unknown_user_is_404(self, admin_client):
        assert admin_client.delete("/users/usr-nope").status_code == 404

    def test_a_non_admin_cannot_remove_anyone(self, viewer_client, repo, auth):
        u = repo.save_user(auth, User(id="", email="a@x.c"))
        assert viewer_client.delete(f"/users/{u.id}").status_code == 403


class TestInvite:
    def test_invites_a_new_email(self, admin_client):
        r = admin_client.post("/users/invite",
                              json={"email": "new@egoiq.com",
                                   "grants": [{"scope": "attendo", "mode": "view"}]})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["email"] == "new@egoiq.com"
        assert body["link"].endswith("/login")
        assert body["emailed"] is False  # no settings/email.json configured in this test
        assert body["status"] == "pending"

    def test_cannot_invite_an_existing_user(self, admin_client, repo, auth):
        repo.save_user(auth, User(id="", email="existing@egoiq.com"))
        r = admin_client.post("/users/invite", json={"email": "existing@egoiq.com", "grants": []})
        assert r.status_code == 409

    def test_cannot_invite_the_same_email_twice_while_pending(self, admin_client):
        admin_client.post("/users/invite", json={"email": "new@egoiq.com", "grants": []})
        r = admin_client.post("/users/invite", json={"email": "new@egoiq.com", "grants": []})
        assert r.status_code == 409

    def test_a_non_admin_cannot_invite(self, viewer_client):
        r = viewer_client.post("/users/invite", json={"email": "a@x.c", "grants": []})
        assert r.status_code == 403


class TestInviteConsumption:
    def test_accepting_an_invite_over_password_registration_gets_its_grants(self, admin_client):
        """The other half of the flow: /auth/register (already built) ends
        at identity.resolve_signed_in_user, which now consumes a pending
        invite (Task 5) -- proven here over the real HTTP surface."""
        admin_client.post("/users/invite",
                          json={"email": "invited@egoiq.com",
                               "grants": [{"scope": "attendo", "mode": "edit"}]})
        r = admin_client.post("/auth/register",
                              json={"email": "invited@egoiq.com",
                                   "password": "correct horse battery staple"})
        assert r.status_code == 201, r.text
        [row] = [u for u in admin_client.get("/users").json() if u["email"] == "invited@egoiq.com"]
        assert row["grants"][0]["scope"] == "attendo"
        [inv] = [i for i in admin_client.get("/invites").json() if i["email"] == "invited@egoiq.com"]
        assert inv["status"] == "accepted"


class TestRevokeInvite:
    def test_revoking_a_pending_invite_removes_it(self, admin_client, repo):
        invite_id = admin_client.post("/users/invite",
                                      json={"email": "a@x.c", "grants": []}).json()["id"]
        r = _delete_approving_consent(admin_client, repo, f"/invites/{invite_id}")
        assert r.status_code == 204
        assert admin_client.get("/invites").json() == []

    def test_revoking_an_accepted_invite_removes_the_user(self, admin_client, repo, auth):
        invite_id = admin_client.post("/users/invite",
                                      json={"email": "a@x.c", "grants": []}).json()["id"]
        admin_client.post("/auth/register",
                          json={"email": "a@x.c", "password": "correct horse battery staple"})
        [row] = [u for u in admin_client.get("/users").json() if u["email"] == "a@x.c"]
        r = _delete_approving_consent(admin_client, repo, f"/invites/{invite_id}")
        assert r.status_code == 204
        assert repo.get_user(auth, row["id"]) is None
