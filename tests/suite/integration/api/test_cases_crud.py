"""Cases CRUD: create/list/rename/delete across the mock (guard/501) and memory (happy path)."""
from __future__ import annotations

import pytest

from reportbuilder.api.deps_store import get_auth, get_repository


def _material_bytes(client, material_id):
    """Read a material's raw bytes straight from the repository client_memory
    is wired to. `memory_hive` is a different, unwritten-to store now that
    client_memory resolves materials through the repository — reading through
    it would only prove the wrong store is empty."""
    repo = client.app.dependency_overrides[get_repository]()
    auth = client.app.dependency_overrides[get_auth]()
    m = repo.find_material(auth, material_id)
    if m is None:
        raise KeyError(material_id)
    return repo.get_material(auth, m.customer_id, m.case_id, m.id)


def _delete_with_consent(client, url):
    """DELETE *url*, approving datahive's consent gate until it succeeds.

    The in-memory seam mirrors datahive's real behaviour: the first delete of
    an object always comes back needing approval (see
    unit/store/test_repository.py's `approve_all` for the same pattern one
    layer down, where the repository is called directly instead of over HTTP).
    """
    repo = client.app.dependency_overrides[get_repository]()
    for _ in range(50):
        resp = client.delete(url)
        if resp.status_code != 409:
            return resp
        repo.store.approve(resp.json()["detail"]["request_id"])
    raise AssertionError("consent loop did not converge")


# --- create / list ----------------------------------------------------------

def test_create_case_returns_case_id(client_mock, mock_hive):
    mock_hive.create_case.return_value = "case-77"
    resp = client_mock.post("/cases", json={"name": "My case"})
    assert resp.status_code == 200
    assert resp.json() == {"case_id": "case-77"}
    mock_hive.create_case.assert_called_once_with("My case")


def test_list_cases_returns_client_payload(client_mock, mock_hive):
    payload = [{"id": "case-1", "name": "A"}, {"id": "case-2", "name": "B"}]
    mock_hive.list_cases.return_value = payload
    resp = client_mock.get("/cases")
    assert resp.status_code == 200
    assert resp.json() == payload


def test_create_then_list_via_memory(client_memory):
    cid = client_memory.post("/cases", json={"name": "Alpha"}).json()["case_id"]
    listing = client_memory.get("/cases").json()
    assert {c["id"]: c["name"] for c in listing}[cid] == "Alpha"


# --- rename -----------------------------------------------------------------

@pytest.mark.parametrize("bad", ["", "   ", "\t\n"])
def test_rename_empty_or_whitespace_is_422(client_memory, bad):
    cust = client_memory.post("/customers", json={"name": "Alpha"}).json()["id"]
    cid = client_memory.post(f"/customers/{cust}/cases", json={"name": "Alpha"}).json()["id"]
    resp = client_memory.patch(f"/cases/{cid}", json={"name": bad})
    assert resp.status_code == 422


def test_rename_updates_listing_via_memory(client_memory):
    cust = client_memory.post("/customers", json={"name": "Alpha"}).json()["id"]
    cid = client_memory.post(f"/customers/{cust}/cases", json={"name": "Alpha"}).json()["id"]
    resp = client_memory.patch(f"/cases/{cid}", json={"name": "Renamed"})
    assert resp.status_code == 200
    assert resp.json() == {"id": cid, "name": "Renamed"}
    listing = {c["id"]: c["name"] for c in client_memory.get("/cases").json()}
    assert listing[cid] == "Renamed"


def test_rename_missing_case_is_404_via_memory(client_memory):
    resp = client_memory.patch("/cases/case-does-not-exist", json={"name": "X"})
    assert resp.status_code == 404


def test_rename_not_supported_is_501_on_mock_spec(client_mock):
    """Mock(spec=DataHiveClient) has no rename_case -> route returns 501."""
    resp = client_mock.patch("/cases/case-1", json={"name": "X"})
    assert resp.status_code == 501


# --- delete -----------------------------------------------------------------

def test_delete_case_cascades_materials_via_memory(client_memory, synthetic_bytes):
    cust = client_memory.post("/customers", json={"name": "Alpha"}).json()["id"]
    cid = client_memory.post(f"/customers/{cust}/cases", json={"name": "Alpha"}).json()["id"]
    up = client_memory.post(
        f"/cases/{cid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    )
    mid = up.json()["material_id"]
    assert _material_bytes(client_memory, mid) == synthetic_bytes  # reachable before delete

    resp = _delete_with_consent(client_memory, f"/cases/{cid}")
    assert resp.status_code == 200
    assert resp.json()["deleted"] == cid

    # Cascade: the case is gone and its material is no longer reachable.
    assert cid not in {c["id"] for c in client_memory.get("/cases").json()}
    with pytest.raises(KeyError):
        _material_bytes(client_memory, mid)


def test_delete_missing_case_is_404_via_memory(client_memory):
    resp = client_memory.delete("/cases/case-nope")
    assert resp.status_code == 404


# Deleted: test_delete_not_supported_is_501_on_mock_spec.
#
# It asserted that a store without `delete_case` makes the route answer 501,
# which the route achieved by probing with getattr(). That probe is why the
# datahive-backed store — which CAN delete — reported "not implemented" to
# users: RepositoryClient simply had no such method yet, and the guard turned
# a missing implementation into a plausible-looking answer instead of an
# error. Deletion is part of the store contract now, so the route calls it
# directly and a store that cannot delete is a bug, not a 501.
