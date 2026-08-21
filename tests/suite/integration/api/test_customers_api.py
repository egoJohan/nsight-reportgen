"""Asiakas/Case API (Trello: Asiakkuuden hallinta).

Drives nSight's own FastAPI app. The store is in-memory, but it enforces path
caveats exactly as datahive does, so the permission tests here mean something.
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
from suite._helpers import sign_in_override

pytestmark = pytest.mark.integration


@pytest.fixture
def store():
    return InMemoryObjectStore()


@pytest.fixture
def client(store):
    app = create_app()
    repo = Repository(store)
    auth = AuthContext(token="user-1")
    app.dependency_overrides[get_repository] = lambda: repo
    app.dependency_overrides[get_auth] = lambda: auth
    app.dependency_overrides[current_user] = sign_in_override(repo, auth)
    return TestClient(app)


def _customer(client, name="Acme Oy"):
    r = client.post("/customers", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


class TestCustomerCrud:
    def test_create_then_appears_in_list(self, client):
        c = _customer(client)
        assert c["name"] == "Acme Oy" and c["id"]
        # Compare identity, not the whole payload: the response also carries the
        # template binding, and asserting on the full dict makes every added
        # field a test failure.
        listed = client.get("/customers").json()
        assert [(x["id"], x["name"]) for x in listed] == [(c["id"], c["name"])]

    def test_get_one(self, client):
        c = _customer(client)
        got = client.get(f"/customers/{c['id']}").json()
        assert (got["id"], got["name"]) == (c["id"], c["name"])

    def test_rename(self, client):
        c = _customer(client, "Vanha")
        r = client.patch(f"/customers/{c['id']}", json={"name": "Uusi"})
        assert r.status_code == 200 and r.json()["name"] == "Uusi"
        assert client.get(f"/customers/{c['id']}").json()["name"] == "Uusi"

    def test_unknown_customer_is_404(self, client):
        assert client.get("/customers/cust-nope").status_code == 404

    @pytest.mark.parametrize("bad", ["", "   "])
    def test_blank_name_refused(self, client, bad):
        assert client.post("/customers", json={"name": bad}).status_code == 422


class TestCaseUnderCustomer:
    def test_case_is_created_under_its_customer(self, client):
        c = _customer(client)
        r = client.post(f"/customers/{c['id']}/cases", json={"name": "Brändi 2026"})
        assert r.status_code == 201
        k = r.json()
        assert k["customer_id"] == c["id"] and k["name"] == "Brändi 2026"
        # The list route adds completed_reports/draft_reports per study
        # (a freshly created case has none of either), so compare on top of
        # the create response's own fields rather than exact equality.
        listed = client.get(f"/customers/{c['id']}/cases").json()
        assert listed == [{**k, "completed_reports": 0, "draft_reports": 0}]

    def test_cases_do_not_leak_between_customers(self, client):
        a, b = _customer(client, "Acme"), _customer(client, "Beta")
        client.post(f"/customers/{a['id']}/cases", json={"name": "A-case"})
        assert client.get(f"/customers/{b['id']}/cases").json() == []

    def test_case_under_unknown_customer_is_404(self, client):
        assert client.post("/customers/cust-nope/cases",
                           json={"name": "X"}).status_code == 404

    def test_rename_case(self, client):
        c = _customer(client)
        k = client.post(f"/customers/{c['id']}/cases", json={"name": "Vanha"}).json()
        r = client.patch(f"/customers/{c['id']}/cases/{k['id']}", json={"name": "Uusi"})
        assert r.status_code == 200 and r.json()["name"] == "Uusi"


class TestStudyReportStats:
    """`completed_reports`/`draft_reports` under each study on
    `GET /customers/{id}/cases` — Empty folds into draft (see
    routes_customers._report_stats)."""

    def test_a_study_with_no_reports_has_no_counts_worth_reading(self, client):
        c = _customer(client)
        client.post(f"/customers/{c['id']}/cases", json={"name": "K"})
        listed = client.get(f"/customers/{c['id']}/cases").json()[0]
        assert listed["completed_reports"] == 0
        assert listed["draft_reports"] == 0

    def test_empty_and_draft_both_count_as_draft_only_a_render_completes(
        self, client, store
    ):
        from reportbuilder.testing.fixtures import report_json_n_charts

        c = _customer(client)
        k = client.post(f"/customers/{c['id']}/cases", json={"name": "K"}).json()

        # Empty: no charts at all.
        client.post(f"/cases/{k['id']}/reports", json=report_json_n_charts(0))
        # Draft: has charts, but no deck has ever been rendered for it.
        client.post(f"/cases/{k['id']}/reports", json=report_json_n_charts(1))
        # Completed: a deck has been stamped onto this one's sidecar.
        rid = client.post(
            f"/cases/{k['id']}/reports", json=report_json_n_charts(2)
        ).json()["report_id"]
        repo = Repository(store)
        auth = AuthContext(token="user-1")
        repo.save_render(auth, k["customer_id"], k["id"], rid, b"fake-pptx", key="k1")

        listed = client.get(f"/customers/{c['id']}/cases").json()[0]
        assert listed["completed_reports"] == 1
        # Empty (1) + Draft (1) folded into one bucket.
        assert listed["draft_reports"] == 2
        # The total must reconcile with what a user sees inside the study.
        reports = client.get(f"/cases/{k['id']}/reports").json()["reports"]
        assert listed["completed_reports"] + listed["draft_reports"] == len(reports)

    def test_counts_do_not_leak_between_studies(self, client):
        from reportbuilder.testing.fixtures import report_json_n_charts

        c = _customer(client)
        k1 = client.post(f"/customers/{c['id']}/cases", json={"name": "K1"}).json()
        k2 = client.post(f"/customers/{c['id']}/cases", json={"name": "K2"}).json()
        client.post(f"/cases/{k1['id']}/reports", json=report_json_n_charts(1))

        listed = {x["id"]: x for x in client.get(f"/customers/{c['id']}/cases").json()}
        assert listed[k1["id"]]["draft_reports"] == 1
        assert listed[k2["id"]]["draft_reports"] == 0
        assert listed[k2["id"]]["completed_reports"] == 0


class TestCustomerListStats:
    """The same statistics, aggregated, plus study count and owners, on
    `GET /customers`."""

    def test_case_count_and_report_stats_are_aggregated_across_studies(
        self, client, store
    ):
        from reportbuilder.testing.fixtures import report_json_n_charts

        c = _customer(client)
        k1 = client.post(f"/customers/{c['id']}/cases", json={"name": "K1"}).json()
        k2 = client.post(f"/customers/{c['id']}/cases", json={"name": "K2"}).json()
        client.post(f"/cases/{k1['id']}/reports", json=report_json_n_charts(1))
        client.post(f"/cases/{k2['id']}/reports", json=report_json_n_charts(0))
        rid = client.post(
            f"/cases/{k2['id']}/reports", json=report_json_n_charts(2)
        ).json()["report_id"]
        repo = Repository(store)
        auth = AuthContext(token="user-1")
        repo.save_render(auth, k2["customer_id"], k2["id"], rid, b"fake", key="k1")

        row = next(x for x in client.get("/customers").json() if x["id"] == c["id"])
        assert row["case_count"] == 2
        assert row["completed_reports"] == 1
        assert row["draft_reports"] == 2  # the K1 draft + the K2 empty

    def test_owners_are_edit_grant_holders_named_where_possible(self, client, store):
        from reportbuilder.auth.permissions import Grant as PermGrant
        from reportbuilder.auth.permissions import User as PermUser

        c = _customer(client)
        repo = Repository(store)
        auth = AuthContext(token="user-1")
        # Named -> shown by name, not email.
        repo.save_user(auth, PermUser(id="", email="alice@example.com", name="Alice A",
                                      grants=(PermGrant(c["id"], "edit"),)))
        # No name on file -> falls back to email.
        repo.save_user(auth, PermUser(id="", email="cara@example.com", name="",
                                      grants=(PermGrant(c["id"], "edit"),)))
        # View only -> not an owner, must not appear.
        repo.save_user(auth, PermUser(id="", email="viewer@example.com", name="Viewer",
                                      grants=(PermGrant(c["id"], "view"),)))

        row = next(x for x in client.get("/customers").json() if x["id"] == c["id"])
        names = {o["name"] for o in row["owners"]}
        assert names == {"Alice A", "cara@example.com"}

    def test_a_customer_with_no_edit_holders_has_no_owners(self, client):
        c = _customer(client)
        row = next(x for x in client.get("/customers").json() if x["id"] == c["id"])
        assert row["owners"] == []


class TestListingIsPermissionFiltered:
    """The UI must never be the security boundary: a caller scoped to one
    customer gets a SHORT list from the server, not a full list to filter.

    Post-D3, nSight holds one tenant-wide service credential — datahive no
    longer scopes anything per caller, so the caller's own Grant/User record is
    what narrows the view, not a token caveat (see `Repository._admits`). A
    caller with a grant on one customer sees only that customer.
    """

    def test_a_scoped_caller_sees_only_their_customer(self, store):
        seed = create_app()
        repo = Repository(store)
        seed_auth = AuthContext(token="admin")
        seed.dependency_overrides[get_repository] = lambda: repo
        seed.dependency_overrides[get_auth] = lambda: seed_auth
        seed.dependency_overrides[current_user] = sign_in_override(repo, seed_auth)
        admin = TestClient(seed)
        a = _customer(admin, "Acme")
        b = _customer(admin, "Beta")
        admin.post(f"/customers/{a['id']}/cases", json={"name": "A-case"})
        admin.post(f"/customers/{b['id']}/cases", json={"name": "B-case"})

        scoped_app = create_app()
        scoped_app.dependency_overrides[get_repository] = lambda: repo
        scoped_app.dependency_overrides[get_auth] = lambda: AuthContext(token="admin")
        scoped_user = User(id="scoped", email="scoped@acme.test", name="Scoped",
                           grants=(Grant(a["id"], "edit"),))
        scoped_app.dependency_overrides[current_user] = lambda: scoped_user
        scoped = TestClient(scoped_app)

        assert [c["id"] for c in scoped.get("/customers").json()] == [a["id"]]
        assert len(scoped.get(f"/customers/{a['id']}/cases").json()) == 1
        # Beta is invisible, and indistinguishable from absent — for the
        # customer itself and for anything scoped under it.
        assert scoped.get(f"/customers/{b['id']}").status_code == 404
        assert scoped.get(f"/customers/{b['id']}/cases").status_code == 404


class TestAuthRequired:
    def test_no_bearer_and_no_dev_token_fails_closed(self, store, monkeypatch):
        monkeypatch.delenv("NSIGHT_DATAHIVE_TOKEN", raising=False)
        app = create_app()
        app.dependency_overrides[get_repository] = lambda: Repository(store)
        # get_auth deliberately NOT overridden — exercise the real dependency.
        assert TestClient(app).get("/customers").status_code == 401


class TestCreateTutkimusFromMaterial:
    """Uploading IS the creation: a tutkimus corresponds to a material, so
    creating one without data leaves an empty shell (Asiakkuuden hallinta)."""

    SAV = bytes([0, 255, 26]) + b"$FL2@(#) SPSS DATA FILE\x00" + bytes(range(64))

    def test_upload_creates_the_tutkimus_named_from_the_file(self, client):
        c = _customer(client)
        r = client.post(f"/customers/{c['id']}/cases/from-material",
                        files={"file": ("Brändiseuranta 2026.sav", self.SAV,
                                        "application/octet-stream")})
        assert r.status_code == 201, r.text
        body = r.json()
        # Extension stripped, the rest left alone — it is the analyst's name.
        assert body["name"] == "Brändiseuranta 2026"
        assert body["customer_id"] == c["id"] and body["material_id"]

    def test_the_material_is_attached_to_that_tutkimus(self, client):
        c = _customer(client)
        created = client.post(f"/customers/{c['id']}/cases/from-material",
                              files={"file": ("s.sav", self.SAV,
                                              "application/octet-stream")}).json()
        mats = client.get(
            f"/customers/{c['id']}/cases/{created['id']}/materials").json()
        assert [m["id"] for m in mats] == [created["material_id"]]
        assert mats[0]["size"] == len(self.SAV)

    def test_the_tutkimus_appears_under_its_customer(self, client):
        c = _customer(client)
        created = client.post(f"/customers/{c['id']}/cases/from-material",
                              files={"file": ("x.sav", self.SAV,
                                              "application/octet-stream")}).json()
        assert [k["id"] for k in client.get(f"/customers/{c['id']}/cases").json()] \
            == [created["id"]]

    def test_an_empty_upload_is_refused(self, client):
        c = _customer(client)
        r = client.post(f"/customers/{c['id']}/cases/from-material",
                        files={"file": ("empty.sav", b"", "application/octet-stream")})
        assert r.status_code == 422

    def test_upload_under_an_unknown_customer_is_404(self, client):
        r = client.post("/customers/cust-nope/cases/from-material",
                        files={"file": ("x.sav", self.SAV, "application/octet-stream")})
        assert r.status_code == 404


class TestLocateMaterial:
    """The question/preview/render routes are keyed by a bare material id from
    before the hierarchy; they resolve the rest through this."""

    def test_locate_returns_the_owning_case_and_customer(self, client):
        c = _customer(client)
        created = client.post(f"/customers/{c['id']}/cases/from-material",
                              files={"file": ("data.sav", b"\x00\x01sav",
                                              "application/octet-stream")}).json()
        found = client.get(f"/materials/{created['material_id']}/locate").json()
        assert found["case_id"] == created["id"]
        assert found["customer_id"] == c["id"]
        assert found["name"] == "data.sav"

    def test_unknown_material_is_404(self, client):
        assert client.get("/materials/mat-nope/locate").status_code == 404
