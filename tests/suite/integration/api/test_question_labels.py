"""PATCH /materials/{id}/questions/{qid}/label — rename a question (case page).

Material-scoped: the rename shows in the material's own /questions list and, via
the shared model seam, in every report/chart/deck using that question. Blank reverts.
"""
from __future__ import annotations


def _case_material(client, synthetic_bytes) -> str:
    cust = client.post("/customers", json={"name": "A"}).json()["id"]
    cid = client.post(f"/customers/{cust}/cases", json={"name": "A"}).json()["id"]
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


# ---- the rename has to survive the report's own view of the questions -------
#
# Reported from staging: a question renamed under Study still showed its
# original SAV label in a report's Select step — "Uskon, että uusi teknologia
# luo kasvua Suomeen" under Study, and the full "…:Seuraavaksi esitämme
# sinulle joukon väittämiä…" in the report.
#
# The two lists are served by different endpoints. `/questions` finalises the
# model, which applies the material's curation; `/regroup` — which is what a
# report asks, because it carries that report's own grouping — built straight
# from the file and applied only the grouping. Every rename and every value
# merge was dropped on the way.

def _regrouped(client, mid, qid):
    body = {"groups": [], "singles": [], "comparisons": []}
    qs = client.post(f"/materials/{mid}/regroup", json=body).json()["questions"]
    return next(q["text"] for q in qs if q["qid"] == qid)


def test_a_rename_survives_regrouping(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    client_memory.patch(f"/materials/{mid}/questions/q1/label", json={"label": "Ikä"})
    assert _text(client_memory, mid, "q1") == "Ikä"          # Study says so
    assert _regrouped(client_memory, mid, "q1") == "Ikä"     # …and so must the report


def test_reverting_a_rename_survives_regrouping_too(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    client_memory.patch(f"/materials/{mid}/questions/q1/label", json={"label": "Ikä"})
    client_memory.patch(f"/materials/{mid}/questions/q1/label", json={"label": ""})
    assert _regrouped(client_memory, mid, "q1") != "Ikä"
