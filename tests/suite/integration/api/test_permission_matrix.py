"""Can one customer's analyst reach another customer's data over HTTP?

Unit tests cover may_read. This covers the whole stack: a real app, a real
store, a user with one grant, and every shape of route the API exposes.

Uses `client_memory` (see conftest.py) rather than a separate fixture: it
already builds the app with NO injected client, so `get_client` constructs the
real `RepositoryClient` over the same object store the guards read through
`app.dependency_overrides`. A fixture that injected a standalone client (as
`client_mock`/a hand-rolled `memory_hive` would) would let routes and guards
disagree about what exists, making every assertion below meaningless.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User


@pytest.fixture
def two_customers(client_memory, synthetic_bytes):
    """Attendo and Synsam, each with a study, a report and a dataset."""
    made = {}
    for name in ("Attendo", "Synsam"):
        cid = client_memory.post("/customers", json={"name": name}).json()["id"]
        kid = client_memory.post(f"/customers/{cid}/cases",
                                 json={"name": f"{name} study"}).json()["id"]
        mid = client_memory.post(
            f"/cases/{kid}/materials",
            files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
        ).json()["material_id"]
        rid = client_memory.post(f"/cases/{kid}/reports",
                                 json={"name": f"{name} report", "render_mode": "image",
                                       "template_ref": "", "charts": []}).json()["report_id"]
        made[name] = {"cid": cid, "kid": kid, "mid": mid, "rid": rid}
    return made


def sign_in(client, monkeypatch, email, *grants, admin=False):
    """Create a user in the store the test app is using, and become them.

    `client_memory` builds its Repository inside the fixture and injects it with
    `app.dependency_overrides` — reaching for the module-level `get_repository()`
    would create a SECOND, empty store and the user would never be found.
    """
    from reportbuilder.api.deps_store import get_auth, get_repository

    overrides = client.app.dependency_overrides
    repo, auth = overrides[get_repository](), overrides[get_auth]()
    repo.save_user(auth, User(id="", email=email, name=email.split("@")[0],
                              is_admin=admin,
                              grants=tuple(Grant(s, m) for s, m in grants)))
    monkeypatch.setenv("NSIGHT_DEV_USER", email)


@pytest.fixture
def as_attendo_editor(client_memory, two_customers, monkeypatch):
    """Sign the client in as someone granted Attendo, edit."""
    sign_in(client_memory, monkeypatch, "maija@egoiq.com",
            (two_customers["Attendo"]["cid"], "edit"))
    return two_customers


def test_the_granted_customer_is_reachable(client_memory, as_attendo_editor):
    a = as_attendo_editor["Attendo"]
    assert client_memory.get(f"/customers/{a['cid']}/cases").status_code == 200
    assert client_memory.get(f"/cases/{a['kid']}/reports").status_code == 200


def test_the_other_customer_is_absent_from_listings(client_memory, as_attendo_editor):
    names = [c["name"] for c in client_memory.get("/customers").json()]
    assert names == ["Attendo"]


def test_the_other_customers_case_is_not_found(client_memory, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_memory.get(f"/cases/{b['kid']}/reports").status_code == 404


def test_the_other_customers_material_is_not_found(client_memory, as_attendo_editor):
    """A material id is not authorisation (spec §5.1)."""
    b = as_attendo_editor["Synsam"]
    assert client_memory.get(f"/materials/{b['mid']}/questions").status_code == 404


def test_the_other_customers_report_cannot_be_read(client_memory, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_memory.get(f"/cases/{b['kid']}/reports/{b['rid']}").status_code == 404


def test_the_other_customers_report_cannot_be_deleted(client_memory, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_memory.delete(f"/cases/{b['kid']}/reports/{b['rid']}").status_code in (403, 404)


def test_recents_shows_only_the_granted_customer(client_memory, as_attendo_editor):
    names = [r["name"] for r in client_memory.get("/reports/recent").json()]
    assert names == ["Attendo report"]


def test_a_viewer_cannot_write(client_memory, two_customers, monkeypatch):
    sign_in(client_memory, monkeypatch, "viewer@egoiq.com",
            (two_customers["Attendo"]["cid"], "view"))
    a = two_customers["Attendo"]
    assert client_memory.get(f"/cases/{a['kid']}/reports").status_code == 200
    assert client_memory.delete(f"/cases/{a['kid']}/reports/{a['rid']}").status_code == 403


def test_the_resolution_cache_does_not_leak_between_users(client_memory, two_customers, monkeypatch):
    """Spec §5.1's cache is per-process and shared. One user resolving their own
    material must not make it resolvable for another."""
    a, b = two_customers["Attendo"], two_customers["Synsam"]
    sign_in(client_memory, monkeypatch, "s@egoiq.com", (b["cid"], "edit"))
    assert client_memory.get(f"/materials/{b['mid']}/questions").status_code == 200

    sign_in(client_memory, monkeypatch, "m@egoiq.com", (a["cid"], "edit"))
    assert client_memory.get(f"/materials/{b['mid']}/questions").status_code == 404


def test_an_admin_without_grants_sees_nothing(client_memory, two_customers, monkeypatch):
    """Administering access is not having access (spec §5)."""
    sign_in(client_memory, monkeypatch, "admin@egoiq.com", admin=True)
    assert client_memory.get("/customers").json() == []
