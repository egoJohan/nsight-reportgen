"""PATCH /materials/{id}/questions/{qid}/label — rename a question (case page).

Material-scoped: the rename shows in the material's own /questions list and, via
the shared model seam, in every report/chart/deck using that question. Blank reverts.
"""
from __future__ import annotations


def _case_material(client, synthetic_bytes) -> str:
    cid = client.post("/cases", json={"name": "A"}).json()["case_id"]
    return client.post(
        f"/cases/{cid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    ).json()["material_id"]


def _text(client, mid, qid):
    qs = client.get(f"/materials/{mid}/questions").json()["questions"]
    return next(q["text"] for q in qs if q["qid"] == qid)


def test_rename_reflected_in_questions_list(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    r = client_memory.patch(f"/materials/{mid}/questions/q1/label", json={"label": "Ikä"})
    assert r.status_code == 200
    assert _text(client_memory, mid, "q1") == "Ikä"


def test_blank_label_reverts_to_original(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    original = _text(client_memory, mid, "q1")
    client_memory.patch(f"/materials/{mid}/questions/q1/label", json={"label": "Temp"})
    client_memory.patch(f"/materials/{mid}/questions/q1/label", json={"label": "  "})
    assert _text(client_memory, mid, "q1") == original


def test_rename_is_material_scoped_not_global(client_memory, synthetic_bytes):
    """Renaming q1 on one material does not touch another material's q1."""
    a = _case_material(client_memory, synthetic_bytes)
    b = _case_material(client_memory, synthetic_bytes)
    b_original = _text(client_memory, b, "q1")
    client_memory.patch(f"/materials/{a}/questions/q1/label", json={"label": "Only A"})
    assert _text(client_memory, a, "q1") == "Only A"
    assert _text(client_memory, b, "q1") == b_original
