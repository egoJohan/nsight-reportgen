"""Material upload: ingest the synthetic SAV through memory (real ingest) and mock seams."""
from __future__ import annotations


def test_upload_via_memory_ingests_and_is_retrievable(client_memory, memory_hive, synthetic_bytes):
    cid = client_memory.post("/cases", json={"name": "C"}).json()["case_id"]
    resp = client_memory.post(
        f"/cases/{cid}/materials",
        files={"file": ("study.sav", synthetic_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"material_id", "question_count", "file_label"}
    assert body["question_count"] > 0
    # Byte-exact material is retrievable from the store.
    assert memory_hive.get_material(body["material_id"]) == synthetic_bytes


def test_upload_response_shape_via_mock(client_mock, mock_hive, synthetic_bytes):
    mock_hive.attach_material.return_value = "mat-42"
    resp = client_mock.post(
        "/cases/case-1/materials",
        files={"file": ("study.sav", synthetic_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["material_id"] == "mat-42"
    assert body["question_count"] > 0
    assert "file_label" in body
    # attach_material was called with (case_id, filename, raw_bytes, codebook_summary).
    args = mock_hive.attach_material.call_args.args
    assert args[0] == "case-1"
    assert args[1] == "study.sav"
    assert args[2] == synthetic_bytes
    assert isinstance(args[3], str) and args[3]
