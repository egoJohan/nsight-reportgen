# tests/suite/integration/api/test_access_requests_api.py
"""GET /customers/{id}/name (the no-access page's one narrow leak) and the
access-request surface behind its "Request access" button: POST
/access-requests, GET /access-requests(/mine), and approve/refuse.
"""
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
    return AuthContext(token="t")


@pytest.fixture
def client(repo, auth):
    """No `current_user` override yet -- a test that wants a signed-out
    request (401) gets that for free by never calling `sign_in`."""
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    return TestClient(app)


def sign_in(client, repo, auth, email, *grants, admin=False) -> User:
    """Same shape as test_permission_matrix.sign_in: a user with EXACTLY the
    grants passed in, no more -- these tests exist to prove a caller with a
    narrow (or no) grant sees and can do only what that grant covers."""
    user = repo.save_user(auth, User(id="", email=email, name=email.split("@")[0],
                                     is_admin=admin,
                                     grants=tuple(Grant(s, m) for s, m in grants)))
    client.app.dependency_overrides[current_user] = lambda: user
    return user


# ---------------------------------------------------------------------------
# GET /customers/{id}/name -- the narrow, deliberate crack in the 404 rule.
# ---------------------------------------------------------------------------

class TestCustomerNameRoute:
    def test_reveals_only_id_and_name_to_an_ungranted_signed_in_user(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "viewer@egoiq.com")  # no grants at all

        r = client.get(f"/customers/{cid}/name")
        assert r.status_code == 200
        assert r.json() == {"id": cid, "name": "Attendo"}

    def test_every_other_customer_route_still_404s_for_that_user(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        repo.create_case(auth, cid, "A study")
        sign_in(client, repo, auth, "viewer@egoiq.com")

        assert client.get(f"/customers/{cid}").status_code == 404
        assert client.get(f"/customers/{cid}/cases").status_code == 404

    def test_404s_for_a_customer_that_does_not_exist(self, client, repo, auth):
        sign_in(client, repo, auth, "viewer@egoiq.com")
        assert client.get("/customers/does-not-exist/name").status_code == 404

    def test_401s_for_a_signed_out_caller(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        assert client.get(f"/customers/{cid}/name").status_code == 401

    def test_works_just_the_same_for_a_granted_user(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "editor@egoiq.com", (cid, "edit"))
        assert client.get(f"/customers/{cid}/name").json() == {"id": cid, "name": "Attendo"}


# ---------------------------------------------------------------------------
# GET /customers/names -- the list form, so the sidebar has something to
# offer for a customer the caller cannot yet open.
# ---------------------------------------------------------------------------

class TestCustomerNamesList:
    def test_lists_every_customer_id_and_name_regardless_of_grant(self, client, repo, auth):
        a = repo.create_customer(auth, "Attendo").id
        b = repo.create_customer(auth, "Holiday Club").id
        sign_in(client, repo, auth, "viewer@egoiq.com")  # no grants at all

        rows = client.get("/customers/names").json()
        assert {r["id"] for r in rows} == {a, b}
        assert {r["name"] for r in rows} == {"Attendo", "Holiday Club"}
        assert all(set(r.keys()) == {"id", "name"} for r in rows)

    def test_401s_for_a_signed_out_caller(self, client, repo, auth):
        repo.create_customer(auth, "Attendo")
        assert client.get("/customers/names").status_code == 401

    def test_an_admin_with_no_grants_still_sees_the_full_roster(self, client, repo, auth):
        """is_admin plays no part in this decision either way -- an admin
        with no grants gets [] from GET /customers (spec §5), but the SAME
        admin gets every name from this route, same as anyone else signed
        in."""
        repo.create_customer(auth, "Attendo")
        sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        assert client.get("/customers").json() == []
        assert len(client.get("/customers/names").json()) == 1

    def test_the_literal_path_is_not_shadowed_by_the_customer_id_route(self, client, repo, auth):
        """Regression guard for the FastAPI route-ordering trap this route's
        docstring warns about: if `/customers/{customer_id}` were matched
        first, "names" would be treated as a customer id and this would
        404 instead of listing."""
        sign_in(client, repo, auth, "viewer@egoiq.com")
        assert client.get("/customers/names").status_code == 200


# ---------------------------------------------------------------------------
# POST /access-requests
# ---------------------------------------------------------------------------

class TestCreateAccessRequest:
    def test_an_ungranted_user_can_request_access(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        user = sign_in(client, repo, auth, "viewer@egoiq.com")

        r = client.post("/access-requests", json={"customer_id": cid, "mode": "view"})
        assert r.status_code == 201
        body = r.json()
        assert body["user_id"] == user.id
        assert body["customer_id"] == cid
        assert body["customer_name"] == "Attendo"
        assert body["mode"] == "view"
        assert body["state"] == "pending"

    def test_a_bad_mode_is_rejected(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "viewer@egoiq.com")
        assert client.post("/access-requests",
                           json={"customer_id": cid, "mode": "delete"}).status_code == 422

    def test_a_nonexistent_customer_404s(self, client, repo, auth):
        sign_in(client, repo, auth, "viewer@egoiq.com")
        r = client.post("/access-requests", json={"customer_id": "nope", "mode": "view"})
        assert r.status_code == 404

    def test_requesting_access_you_already_have_is_refused(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "editor@egoiq.com", (cid, "edit"))
        r = client.post("/access-requests", json={"customer_id": cid, "mode": "view"})
        assert r.status_code == 409

    def test_a_viewer_may_still_request_an_upgrade_to_edit(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "viewer@egoiq.com", (cid, "view"))
        r = client.post("/access-requests", json={"customer_id": cid, "mode": "edit"})
        assert r.status_code == 201

    def test_a_second_pending_request_replaces_the_first_rather_than_piling_up(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        user = sign_in(client, repo, auth, "viewer@egoiq.com")

        first = client.post("/access-requests", json={"customer_id": cid, "mode": "view"}).json()
        second = client.post("/access-requests", json={"customer_id": cid, "mode": "edit"}).json()
        assert second["id"] == first["id"]
        assert second["mode"] == "edit"

        mine = repo.list_access_requests_for_user(auth, user.id)
        assert len(mine) == 1
        assert mine[0].mode == "edit"

    def test_extra_user_id_in_the_body_is_ignored_not_honoured(self, client, repo, auth):
        """A user cannot request on someone else's behalf: the requester is
        always taken from the session, and the route's body model has no
        `user_id` field for a caller to smuggle one through."""
        cid = repo.create_customer(auth, "Attendo").id
        me = sign_in(client, repo, auth, "attacker@egoiq.com")
        victim = repo.save_user(auth, User(id="", email="victim@egoiq.com"))

        r = client.post("/access-requests",
                        json={"customer_id": cid, "mode": "edit", "user_id": victim.id})
        assert r.status_code == 201
        assert r.json()["user_id"] == me.id
        assert repo.list_access_requests_for_user(auth, victim.id) == []


# ---------------------------------------------------------------------------
# GET /access-requests/mine and GET /access-requests
# ---------------------------------------------------------------------------

class TestListAccessRequests:
    def test_mine_returns_only_the_callers_own_requests(self, client, repo, auth):
        a = repo.create_customer(auth, "Attendo").id
        b = repo.create_customer(auth, "Synsam").id
        sign_in(client, repo, auth, "one@egoiq.com")
        client.post("/access-requests", json={"customer_id": a, "mode": "view"})

        sign_in(client, repo, auth, "two@egoiq.com")
        client.post("/access-requests", json={"customer_id": b, "mode": "view"})

        mine = client.get("/access-requests/mine").json()
        assert len(mine) == 1
        assert mine[0]["customer_id"] == b

    def test_a_viewer_sees_no_requests_at_all(self, client, repo, auth):
        """Not a 403: having nothing to decide is not being refused a
        permission, it's just an empty queue. A `view` grant on the very
        customer a request names is still not ownership."""
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "requester@egoiq.com")
        client.post("/access-requests", json={"customer_id": cid, "mode": "edit"})

        sign_in(client, repo, auth, "viewer@egoiq.com", (cid, "view"))
        r = client.get("/access-requests")
        assert r.status_code == 200
        assert r.json() == []

    def test_someone_with_no_grant_at_all_sees_no_requests(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "requester@egoiq.com")
        client.post("/access-requests", json={"customer_id": cid, "mode": "view"})

        sign_in(client, repo, auth, "nobody@egoiq.com")
        assert client.get("/access-requests").json() == []

    def test_an_admin_sees_every_pending_request(self, client, repo, auth):
        a = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "viewer@egoiq.com")
        client.post("/access-requests", json={"customer_id": a, "mode": "view"})

        sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        rows = client.get("/access-requests").json()
        assert len(rows) == 1
        assert rows[0]["state"] == "pending"

    def test_an_owner_sees_only_their_own_customers_requests(self, client, repo, auth):
        """The core of the matrix: an owner (`edit` on Attendo) sees
        Attendo's pending request and NOT Synsam's, even with both pending
        at once -- this is a filter on the listing, not a separate
        permission, so it has to actually discriminate between two
        customers, not just between "some" and "none"."""
        attendo = repo.create_customer(auth, "Attendo").id
        synsam = repo.create_customer(auth, "Synsam").id
        sign_in(client, repo, auth, "requester@egoiq.com")
        client.post("/access-requests", json={"customer_id": attendo, "mode": "edit"})
        client.post("/access-requests", json={"customer_id": synsam, "mode": "edit"})

        sign_in(client, repo, auth, "owner@egoiq.com", (attendo, "edit"))
        rows = client.get("/access-requests").json()
        assert [r["customer_id"] for r in rows] == [attendo]

    def test_decided_requests_do_not_appear_in_the_queue(self, client, repo, auth):
        """Granted and refused requests are history, not queue -- the record
        itself is untouched (state/decided_by/decided_at all still readable
        via /access-requests/mine, see TestApproveAndRefuse), but this
        listing only ever shows what still needs deciding, for admin and
        owner alike."""
        a = repo.create_customer(auth, "Attendo").id
        b = repo.create_customer(auth, "Synsam").id
        sign_in(client, repo, auth, "requester@egoiq.com")
        granted_id = client.post("/access-requests", json={"customer_id": a, "mode": "view"}).json()["id"]
        client.post("/access-requests", json={"customer_id": b, "mode": "view"})

        sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        client.post(f"/access-requests/{granted_id}/approve")

        rows = client.get("/access-requests").json()
        assert [r["customer_id"] for r in rows] == [b]


# ---------------------------------------------------------------------------
# approve / refuse
# ---------------------------------------------------------------------------

class TestApproveAndRefuse:
    def test_approving_grants_exactly_the_requested_mode(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        user = sign_in(client, repo, auth, "viewer@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": cid, "mode": "edit"}).json()["id"]

        sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        r = client.post(f"/access-requests/{rid}/approve")
        assert r.status_code == 200
        assert r.json()["state"] == "granted"

        granted = repo.get_user(auth, user.id)
        assert granted.grants == (Grant(cid, "edit"),)

    def test_approving_preserves_the_users_other_grants(self, client, repo, auth):
        a = repo.create_customer(auth, "Attendo").id
        b = repo.create_customer(auth, "Synsam").id
        user = sign_in(client, repo, auth, "viewer@egoiq.com", (a, "view"))
        rid = client.post("/access-requests", json={"customer_id": b, "mode": "view"}).json()["id"]

        sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        client.post(f"/access-requests/{rid}/approve")

        scopes = {g.scope: g.mode for g in repo.get_user(auth, user.id).grants}
        assert scopes == {a: "view", b: "view"}

    def test_refusing_marks_refused_and_grants_nothing(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        user = sign_in(client, repo, auth, "viewer@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": cid, "mode": "view"}).json()["id"]

        sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        r = client.post(f"/access-requests/{rid}/refuse")
        assert r.status_code == 200
        assert r.json()["state"] == "refused"
        assert repo.get_user(auth, user.id).grants == ()

    def test_a_decided_request_cannot_be_decided_again(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "viewer@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": cid, "mode": "view"}).json()["id"]

        sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        client.post(f"/access-requests/{rid}/approve")
        assert client.post(f"/access-requests/{rid}/refuse").status_code == 409

    def test_an_unknown_request_id_404s(self, client, repo, auth):
        sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        assert client.post("/access-requests/nope/approve").status_code == 404
        assert client.post("/access-requests/nope/refuse").status_code == 404

    # -- who may decide: admin, or the customer's owner (edit) -------------
    #
    # There used to be a test here (`test_an_admin_cannot_approve_their_own_
    # request`) pinning a self-approval ban. The ban itself is gone --
    # see routes_access_requests._require_decider's docstring for why -- and
    # with it that test has no rule left to assert; keeping it would mean
    # either deleting the assertion (leaving a test that tests nothing) or
    # flipping it to assert the opposite with no more coverage than the
    # owner self-decision tests below already give it, so it is removed
    # rather than limping on as either. `test_edit_holder_cannot_approve_
    # their_own_request_for_a_different_customer` and `test_an_owner_may_
    # approve_their_own_request_for_a_customer_they_already_own` below are
    # what now carries that weight -- self-decision is fine when the scope
    # check passes, refused when it doesn't, same as anyone else.

    def test_a_non_admin_with_no_stake_in_the_customer_cannot_approve_or_refuse(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "viewer@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": cid, "mode": "view"}).json()["id"]

        sign_in(client, repo, auth, "other@egoiq.com")
        assert client.post(f"/access-requests/{rid}/approve").status_code == 403
        assert client.post(f"/access-requests/{rid}/refuse").status_code == 403

    def test_a_viewer_cannot_approve_or_refuse_even_for_their_own_customer(self, client, repo, auth):
        """`view` is not ownership -- only `edit` is (see permissions.py)."""
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "requester@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": cid, "mode": "edit"}).json()["id"]

        sign_in(client, repo, auth, "viewer@egoiq.com", (cid, "view"))
        assert client.post(f"/access-requests/{rid}/approve").status_code == 403
        assert client.post(f"/access-requests/{rid}/refuse").status_code == 403

    def test_an_owner_may_approve_a_request_for_their_own_customer(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        requester = sign_in(client, repo, auth, "requester@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": cid, "mode": "edit"}).json()["id"]

        sign_in(client, repo, auth, "owner@egoiq.com", (cid, "edit"))
        r = client.post(f"/access-requests/{rid}/approve")
        assert r.status_code == 200
        assert r.json()["state"] == "granted"
        assert repo.get_user(auth, requester.id).grants == (Grant(cid, "edit"),)

    def test_an_owner_may_refuse_a_request_for_their_own_customer(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        sign_in(client, repo, auth, "requester@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": cid, "mode": "view"}).json()["id"]

        sign_in(client, repo, auth, "owner@egoiq.com", (cid, "edit"))
        r = client.post(f"/access-requests/{rid}/refuse")
        assert r.status_code == 200
        assert r.json()["state"] == "refused"

    def test_an_owner_cannot_approve_a_request_for_a_different_customer(self, client, repo, auth):
        """The customer-scope check on its own, with no self-decision angle
        at all -- the requester and the owner are two different people, and
        that alone is not enough: 'owner@egoiq.com' owns Attendo, the
        request names Synsam, and holding edit on the wrong customer is the
        same as holding none. This is the check that now does ALL the work
        the removed self-approval ban used to share with it."""
        attendo = repo.create_customer(auth, "Attendo").id
        synsam = repo.create_customer(auth, "Synsam").id
        sign_in(client, repo, auth, "requester@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": synsam, "mode": "edit"}).json()["id"]

        sign_in(client, repo, auth, "owner@egoiq.com", (attendo, "edit"))
        assert client.post(f"/access-requests/{rid}/approve").status_code == 403
        assert client.post(f"/access-requests/{rid}/refuse").status_code == 403

    def test_edit_holder_cannot_approve_their_own_request_for_a_different_customer(self, client, repo, auth):
        """Same check as above, but requester and decider ARE the same
        identity -- the "obvious hole" a self-approval ban might seem to
        guard against. It doesn't need one: 'owner@egoiq.com' holds edit on
        Attendo, files their OWN request for Synsam, and still cannot
        approve it, because they hold no edit on Synsam. Nothing about it
        being their own request changes the answer."""
        attendo = repo.create_customer(auth, "Attendo").id
        synsam = repo.create_customer(auth, "Synsam").id
        owner = sign_in(client, repo, auth, "owner@egoiq.com", (attendo, "edit"))
        rid = client.post("/access-requests", json={"customer_id": synsam, "mode": "edit"}).json()["id"]

        r = client.post(f"/access-requests/{rid}/approve")
        assert r.status_code == 403
        assert repo.get_user(auth, owner.id).grants == (Grant(attendo, "edit"),)

    def test_an_owner_may_approve_their_own_request_for_a_customer_they_already_own(self, client, repo, auth):
        """Filing this through POST /access-requests is impossible -- you
        cannot request access you already have, it 409s -- so the pending
        request here is created directly through the repository, standing
        in for one that predates a grant change. It proves the scope check
        ALONE, with no self-check behind it, is what decides this even when
        requester and decider are the very same identity."""
        cid = repo.create_customer(auth, "Attendo").id
        owner = sign_in(client, repo, auth, "owner@egoiq.com", (cid, "edit"))
        req = repo.create_access_request(auth, user_id=owner.id, user_email=owner.email,
                                         customer_id=cid, mode="edit")

        r = client.post(f"/access-requests/{req.id}/approve")
        assert r.status_code == 200
        assert r.json()["state"] == "granted"

    def test_approving_grants_the_requester_never_the_approving_admin(self, client, repo, auth):
        cid = repo.create_customer(auth, "Attendo").id
        requester = sign_in(client, repo, auth, "viewer@egoiq.com")
        rid = client.post("/access-requests", json={"customer_id": cid, "mode": "view"}).json()["id"]

        admin = sign_in(client, repo, auth, "admin@egoiq.com", admin=True)
        client.post(f"/access-requests/{rid}/approve")

        assert repo.get_user(auth, requester.id).grants == (Grant(cid, "view"),)
        assert repo.get_user(auth, admin.id).grants == ()
