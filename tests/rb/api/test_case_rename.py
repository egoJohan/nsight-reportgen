"""Case rename (PATCH /cases/{id}) + upload exposes the SAV study label."""
from __future__ import annotations

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.store.memory_client import InMemoryDataHiveClient


def _client():
    return TestClient(create_app(client=InMemoryDataHiveClient()))


def test_rename_case_updates_the_listing():
    c = _client()
    cid = c.post("/cases", json={"name": "from file name"}).json()["case_id"]

    r = c.patch(f"/cases/{cid}", json={"name": "Attendo Brand 2025"})
    assert r.status_code == 200
    assert r.json()["name"] == "Attendo Brand 2025"

    cases = {x["id"]: x for x in c.get("/cases").json()}
    assert cases[cid]["name"] == "Attendo Brand 2025"


def test_rename_missing_case_404():
    assert _client().patch("/cases/nope", json={"name": "x"}).status_code == 404


def test_delete_case_removes_it():
    c = _client()
    cid = c.post("/cases", json={"name": "to delete"}).json()["case_id"]
    assert c.delete(f"/cases/{cid}").status_code == 200
    assert cid not in [x["id"] for x in c.get("/cases").json()]
    # Deleting again is a 404.
    assert c.delete(f"/cases/{cid}").status_code == 404


def test_rename_empty_name_422():
    c = _client()
    cid = c.post("/cases", json={"name": "x"}).json()["case_id"]
    assert c.patch(f"/cases/{cid}", json={"name": "   "}).status_code == 422


def test_upload_response_includes_file_label_key():
    """The upload payload carries file_label (SAV study title; null when absent)
    so the UI can name the case from the file."""
    import io
    from reportbuilder.testing.fixtures import synthetic_sav_bytes

    c = _client()
    cid = c.post("/cases", json={"name": "tmp"}).json()["case_id"]
    files = {"file": ("survey.sav", io.BytesIO(synthetic_sav_bytes()), "application/octet-stream")}
    r = c.post(f"/cases/{cid}/materials", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "file_label" in body  # present (value may be null for a label-less SAV)
    assert "material_id" in body and "question_count" in body
