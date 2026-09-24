"""Material upload: ingest the synthetic SAV through memory (real ingest) and mock seams."""
from __future__ import annotations

from reportbuilder.api.deps_store import get_auth, get_repository


def _material_bytes(client, material_id):
    """Read a material's raw bytes straight from the repository client_memory
    is wired to. `memory_hive` is a different, unwritten-to store now that
    client_memory resolves materials through the repository — reading through
    it would only prove the wrong store is empty."""
    repo = client.app.dependency_overrides[get_repository]()
    auth = client.app.dependency_overrides[get_auth]()
    m = repo.find_material(auth, material_id)
    return repo.get_material(auth, m.customer_id, m.case_id, m.id)


def test_upload_via_memory_ingests_and_is_retrievable(client_memory, synthetic_bytes):
    cust = client_memory.post("/customers", json={"name": "C"}).json()["id"]
    cid = client_memory.post(f"/customers/{cust}/cases", json={"name": "C"}).json()["id"]
    resp = client_memory.post(
        f"/cases/{cid}/materials",
        files={"file": ("study.sav", synthetic_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"material_id", "question_count", "file_label"}
    assert body["question_count"] > 0
    # Byte-exact material is retrievable from the store.
    assert _material_bytes(client_memory, body["material_id"]) == synthetic_bytes


def test_upload_response_shape_via_mock(client_mock, mock_hive, synthetic_bytes):
    mock_hive.attach_material.return_value = "mat-42"
    resp = client_mock.post(
        f"/cases/{client_mock.case_id}/materials",
        files={"file": ("study.sav", synthetic_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["material_id"] == "mat-42"
    assert body["question_count"] > 0
    assert "file_label" in body
    # attach_material was called with (case_id, filename, raw_bytes, codebook_summary).
    args = mock_hive.attach_material.call_args.args
    assert args[0] == client_mock.case_id
    assert args[1] == "study.sav"
    assert args[2] == synthetic_bytes
    assert isinstance(args[3], str) and args[3]


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


def _seed(client, synthetic_bytes, *, reports=()):
    """A tutkimus with a dataset and, optionally, reports built on it."""
    cust = client.post("/customers", json={"name": "C"}).json()["id"]
    cid = client.post(f"/customers/{cust}/cases", json={"name": "C"}).json()["id"]
    mid = client.post(
        f"/cases/{cid}/materials",
        files={"file": ("study.sav", synthetic_bytes, "application/octet-stream")},
    ).json()["material_id"]
    for name in reports:
        client.post(f"/cases/{cid}/reports",
                    json={"name": name, "render_mode": "image",
                          "template_ref": "", "charts": []})
    return cid, mid


def test_deleting_a_dataset_that_is_not_there_is_a_404(client_memory, synthetic_bytes):
    cid, _mid = _seed(client_memory, synthetic_bytes)
    assert client_memory.delete(f"/cases/{cid}/materials/mat-nope").status_code == 404


# Deleting a study's last dataset makes it read-only for good (spec
# 2026-09-24): see test_dataset_deletion_api.py, which replaced the tests of the
# earlier rule — reports kept and emptied, the study left for the next import.
