"""Case rename (PATCH /cases/{id}) + upload exposes the SAV study label."""
from __future__ import annotations

import io

from reportbuilder.testing.fixtures import synthetic_sav_bytes


def test_rename_case_updates_the_listing(rb_client_memory):
    c = rb_client_memory

    r = c.patch(f"/cases/{c.case_id}", json={"name": "Attendo Brand 2025"})
    assert r.status_code == 200
    assert r.json()["name"] == "Attendo Brand 2025"

    cases = {x["id"]: x for x in c.get("/cases").json()}
    assert cases[c.case_id]["name"] == "Attendo Brand 2025"


def test_rename_missing_case_404(rb_client_memory):
    assert rb_client_memory.patch("/cases/nope", json={"name": "x"}).status_code == 404


def test_delete_case_removes_it(rb_client_memory, delete_with_consent):
    c = rb_client_memory
    assert delete_with_consent(c, f"/cases/{c.case_id}").status_code == 200
    assert c.case_id not in [x["id"] for x in c.get("/cases").json()]
    # Deleting again is a 404.
    assert c.delete(f"/cases/{c.case_id}").status_code == 404


def test_rename_empty_name_422(rb_client_memory):
    c = rb_client_memory
    assert c.patch(f"/cases/{c.case_id}", json={"name": "   "}).status_code == 422


def test_upload_response_includes_file_label_key(rb_client_memory):
    """The upload payload carries file_label (SAV study title; null when absent)
    so the UI can name the case from the file."""
    c = rb_client_memory
    files = {"file": ("survey.sav", io.BytesIO(synthetic_sav_bytes()), "application/octet-stream")}
    r = c.post(f"/cases/{c.case_id}/materials", files=files)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "file_label" in body  # present (value may be null for a label-less SAV)
    assert "material_id" in body and "question_count" in body
