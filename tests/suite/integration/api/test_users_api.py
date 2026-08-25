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


class TestGrantableCustomers:
    """GET /users/customers -- the grant picker's feed, deliberately
    unfiltered by grants (task-11): an admin with none yet must still be
    able to name a customer in a grant, or nobody can ever be granted
    anything, including that admin."""

    def test_an_admin_with_no_grants_still_sees_every_customer_here(self, repo, auth):
        app = create_app()
        app.dependency_overrides[get_repository] = lambda: repo
        app.dependency_overrides[get_auth] = lambda: auth
        cid = repo.create_customer(auth, "Attendo").id
        admin = User(id="admin", email="admin@x.c", name="admin", is_admin=True, grants=())
        app.dependency_overrides[current_user] = lambda: admin
        client = TestClient(app)

        # The rule this route exists around, restated: the grant-filtered
        # listing sees nothing for this admin.
        assert client.get("/customers").json() == []
        # The admin-only listing exists precisely so that is not a dead end.
        assert client.get("/users/customers").json() == [{"id": cid, "name": "Attendo"}]

    def test_it_returns_only_id_and_name(self, admin_client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        row = admin_client.get("/users/customers").json()[0]
        assert row == {"id": cid, "name": "Attendo"}

    def test_a_non_admin_cannot_list_it_either(self, viewer_client):
        assert viewer_client.get("/users/customers").status_code == 403


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
    def test_inviting_creates_the_account_there_and_then(self, admin_client, repo, auth):
        """An invitation invites someone to SIGN IN, not to create an account.

        The account and its grants exist from the moment the admin invites, so
        there is never a window where an address is spoken for but unclaimed.
        That window was the bug: `/auth/register` refuses any email that
        already resolves to an account precisely so nobody can claim a
        colleague's access by knowing their address — and the guard could not
        fire while the account did not exist yet.
        """
        admin_client.post("/users/invite",
                          json={"email": "new@egoiq.com",
                                "grants": [{"scope": "attendo", "mode": "view"}]})
        u = repo.find_user_by_email(auth, "new@egoiq.com")
        assert u is not None, "the invited account must exist immediately"
        assert [(g.scope, g.mode) for g in u.grants] == [("attendo", "view")]
        assert u.is_admin is False

    def test_the_invited_account_has_no_password_to_guess(self, admin_client, repo, auth):
        """Nothing sets one. Sign-in is Google or Microsoft."""
        admin_client.post("/users/invite", json={"email": "new@egoiq.com", "grants": []})
        u = repo.find_user_by_email(auth, "new@egoiq.com")
        assert repo.get_password_hash(auth, u.id) is None

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
    def test_an_invited_address_cannot_be_claimed_by_a_stranger(self, admin_client):
        """The guard that could not fire before.

        `/auth/register` refuses any email that already resolves to an account,
        so that nobody can take a colleague's access by knowing their address.
        While the account was only created at first sign-in, there was nothing
        for it to refuse: whoever presented the address first was handed the
        invitation's grants and a working session.
        """
        admin_client.post("/users/invite",
                          json={"email": "invited@egoiq.com",
                               "grants": [{"scope": "attendo", "mode": "edit"}]})
        r = admin_client.post("/auth/register",
                              json={"email": "invited@egoiq.com",
                                   "password": "correct horse battery staple"})
        assert r.status_code == 403, r.text

    def test_the_grants_are_on_the_account_from_the_start(self, admin_client):
        admin_client.post("/users/invite",
                          json={"email": "invited@egoiq.com",
                               "grants": [{"scope": "attendo", "mode": "edit"}]})
        [row] = [u for u in admin_client.get("/users").json()
                 if u["email"] == "invited@egoiq.com"]
        assert row["grants"][0]["scope"] == "attendo"
        [inv] = [i for i in admin_client.get("/invites").json()
                 if i["email"] == "invited@egoiq.com"]
        assert inv["status"] == "pending", "pending until they actually sign in"


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


class TestRevokeCreatesNoOrphan:
    def test_revoking_a_pending_invite_removes_the_account_too(
        self, admin_client, repo, auth
    ):
        """The account exists from the moment of invitation, so revoking has to
        take it away. Deleting only the invite record would leave the account
        holding exactly the grants the admin just decided to withdraw — and it
        would read as "revoked" on the invites screen."""
        admin_client.post("/users/invite",
                          json={"email": "gone@egoiq.com",
                                "grants": [{"scope": "attendo", "mode": "edit"}]})
        assert repo.find_user_by_email(auth, "gone@egoiq.com") is not None
        [inv] = [i for i in admin_client.get("/invites").json()
                 if i["email"] == "gone@egoiq.com"]
        d = _delete_approving_consent(admin_client, repo, f"/invites/{inv['id']}")
        assert d.status_code == 204, d.text
        assert repo.find_user_by_email(auth, "gone@egoiq.com") is None
