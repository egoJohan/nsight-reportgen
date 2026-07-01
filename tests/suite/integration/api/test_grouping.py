"""POST /materials/{id}/regroup — stateless grouping PREVIEW for the report wizard.

Returns the reshaped question list for a given override, WITHOUT persisting (the
override is saved with the report). Grouping is report-specific, not material-level,
so the material's own /questions list is unaffected.
"""
from __future__ import annotations


def _case_material(client, synthetic_bytes) -> str:
    cid = client.post("/cases", json={"name": "A"}).json()["case_id"]
    return client.post(
        f"/cases/{cid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    ).json()["material_id"]


def test_regroup_combines(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    body = {"groups": [{"kind": "multi", "variables": ["q1", "m1"], "label": "Combo"}], "singles": []}
    r = client_memory.post(f"/materials/{mid}/regroup", json=body)
    assert r.status_code == 200
    combo = [q for q in r.json()["questions"]
             if q["kind"] == "multi" and set(q["variables"]) == {"q1", "m1"}]
    assert combo and combo[0]["text"] == "Combo"


def test_regroup_is_stateless(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    # synthetic auto-groups m1+m2 into one multi.
    before = client_memory.get(f"/materials/{mid}/questions").json()["questions"]
    assert any(q["kind"] == "multi" for q in before)

    reshaped = client_memory.post(
        f"/materials/{mid}/regroup", json={"groups": [], "singles": ["m1", "m2"]}
    ).json()["questions"]
    assert not any(q["kind"] == "multi" for q in reshaped)  # split in the preview

    # The material's own list is UNCHANGED (nothing persisted).
    after = client_memory.get(f"/materials/{mid}/questions").json()["questions"]
    assert any(q["kind"] == "multi" for q in after)


def test_regroup_validation_422s(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    def post(groups):
        return client_memory.post(f"/materials/{mid}/regroup",
                                  json={"groups": groups, "singles": []})
    assert post([{"kind": "multi", "variables": ["q1"]}]).status_code == 422           # <2
    assert post([{"kind": "multi", "variables": ["q1", "ghost"]}]).status_code == 422   # unknown
    assert post([{"kind": "multi", "variables": ["q1", "age"]}]).status_code == 422     # scale
    assert post([{"kind": "multi", "variables": ["q1", "m1"]},
                 {"kind": "multi", "variables": ["m1", "m2"]}]).status_code == 422       # double-assign


def test_regroup_returns_full_question_payload(client_memory, synthetic_bytes):
    """The reshaped list carries the browse fields (suggested chart type, etc.)."""
    mid = _case_material(client_memory, synthetic_bytes)
    q = client_memory.post(f"/materials/{mid}/regroup", json={"groups": [], "singles": []}).json()["questions"][0]
    for key in ("qid", "kind", "variables", "text", "chartable", "suggested_chart_type"):
        assert key in q


def test_variables_include_all_is_superset(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    base = client_memory.get(f"/materials/{mid}/variables").json()["variables"]
    allv = client_memory.get(f"/materials/{mid}/variables?include_all=true").json()["variables"]
    assert len(allv) >= len(base)
