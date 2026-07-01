"""Reports CRUD + duplicate round-trip against the real InMemory store."""
from __future__ import annotations

import pytest

from reportbuilder.testing.fixtures import report_json_n_charts


@pytest.fixture
def case_id(client_memory):
    return client_memory.post("/cases", json={"name": "C"}).json()["case_id"]


def _report_body():
    """A valid raw Report dict (name 'R-1', one chart)."""
    return report_json_n_charts(1)


# --- create / get -----------------------------------------------------------

def test_create_returns_report_id(client_memory, case_id):
    resp = client_memory.post(f"/cases/{case_id}/reports", json=_report_body())
    assert resp.status_code == 200
    assert isinstance(resp.json()["report_id"], str)


def test_get_returns_parsed_report_json(client_memory, case_id):
    rid = client_memory.post(f"/cases/{case_id}/reports", json=_report_body()).json()["report_id"]
    resp = client_memory.get(f"/cases/{case_id}/reports/{rid}")
    assert resp.status_code == 200
    assert resp.json()["name"] == "R-1"


def test_get_missing_report_is_404(client_memory, case_id):
    resp = client_memory.get(f"/cases/{case_id}/reports/rep-missing")
    assert resp.status_code == 404


def test_create_invalid_body_is_422(client_memory, case_id):
    resp = client_memory.post(f"/cases/{case_id}/reports", json={"not": "a report"})
    assert resp.status_code == 422


# --- update -----------------------------------------------------------------

def test_put_replaces_existing(client_memory, case_id):
    rid = client_memory.post(f"/cases/{case_id}/reports", json=_report_body()).json()["report_id"]
    body = _report_body()
    body["name"] = "Renamed report"
    resp = client_memory.put(f"/cases/{case_id}/reports/{rid}", json=body)
    assert resp.status_code == 200
    assert resp.json()["report_id"] == rid
    assert client_memory.get(f"/cases/{case_id}/reports/{rid}").json()["name"] == "Renamed report"


def test_put_invalid_body_is_422(client_memory, case_id):
    rid = client_memory.post(f"/cases/{case_id}/reports", json=_report_body()).json()["report_id"]
    resp = client_memory.put(f"/cases/{case_id}/reports/{rid}", json={"bad": "body"})
    assert resp.status_code == 422


def test_put_after_delete_does_not_resurrect(client_memory, case_id):
    rid = client_memory.post(f"/cases/{case_id}/reports", json=_report_body()).json()["report_id"]
    assert client_memory.delete(f"/cases/{case_id}/reports/{rid}").status_code == 200
    resp = client_memory.put(f"/cases/{case_id}/reports/{rid}", json=_report_body())
    assert resp.status_code == 404
    # Still gone: not resurrected.
    assert client_memory.get(f"/cases/{case_id}/reports/{rid}").status_code == 404


# --- delete -----------------------------------------------------------------

def test_delete_then_get_is_404(client_memory, case_id):
    rid = client_memory.post(f"/cases/{case_id}/reports", json=_report_body()).json()["report_id"]
    resp = client_memory.delete(f"/cases/{case_id}/reports/{rid}")
    assert resp.status_code == 200
    assert resp.json() == {"deleted": rid}
    assert client_memory.get(f"/cases/{case_id}/reports/{rid}").status_code == 404


# --- duplicate --------------------------------------------------------------

def test_duplicate_makes_new_id_with_new_name(client_memory, case_id):
    rid = client_memory.post(f"/cases/{case_id}/reports", json=_report_body()).json()["report_id"]
    resp = client_memory.post(
        f"/cases/{case_id}/reports/{rid}/duplicate", json={"name": "Copy of R-1"}
    )
    assert resp.status_code == 200
    new_id = resp.json()["report_id"]
    assert new_id != rid
    # New name is baked into the duplicated doc; the original is untouched.
    assert client_memory.get(f"/cases/{case_id}/reports/{new_id}").json()["name"] == "Copy of R-1"
    assert client_memory.get(f"/cases/{case_id}/reports/{rid}").json()["name"] == "R-1"
