"""Cases CRUD: create/list/rename/delete across the mock (guard/501) and memory (happy path)."""
from __future__ import annotations

import pytest


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
    cid = client_memory.post("/cases", json={"name": "Alpha"}).json()["case_id"]
    resp = client_memory.patch(f"/cases/{cid}", json={"name": bad})
    assert resp.status_code == 422


def test_rename_updates_listing_via_memory(client_memory):
    cid = client_memory.post("/cases", json={"name": "Alpha"}).json()["case_id"]
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

def test_delete_case_cascades_materials_via_memory(client_memory, memory_hive, synthetic_bytes):
    cid = client_memory.post("/cases", json={"name": "Alpha"}).json()["case_id"]
    up = client_memory.post(
        f"/cases/{cid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    )
    mid = up.json()["material_id"]
    assert memory_hive.get_material(mid) == synthetic_bytes  # reachable before delete

    resp = client_memory.delete(f"/cases/{cid}")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": cid}

    # Cascade: the case is gone and its material is no longer reachable.
    assert cid not in {c["id"] for c in client_memory.get("/cases").json()}
    with pytest.raises((KeyError, FileNotFoundError, OSError)):
        memory_hive.get_material(mid)


def test_delete_missing_case_is_404_via_memory(client_memory):
    resp = client_memory.delete("/cases/case-nope")
    assert resp.status_code == 404


def test_delete_not_supported_is_501_on_mock_spec(client_mock):
    """Mock(spec=DataHiveClient) has no delete_case -> route returns 501."""
    resp = client_mock.delete("/cases/case-1")
    assert resp.status_code == 501
