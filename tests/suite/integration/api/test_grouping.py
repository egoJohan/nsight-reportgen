"""GET/PUT /materials/{id}/grouping — persisted manual grouping override, and its
effect on the reshaped question model (through the centralized loader).
"""
from __future__ import annotations


def _case_material(client, synthetic_bytes) -> str:
    cid = client.post("/cases", json={"name": "A"}).json()["case_id"]
    mid = client.post(
        f"/cases/{cid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    ).json()["material_id"]
    return mid


def test_get_grouping_empty_by_default(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    assert client_memory.get(f"/materials/{mid}/grouping").json()["override"] == {
        "groups": [], "singles": []
    }


def test_put_combines_persists_and_reshapes(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    body = {"groups": [{"kind": "multi", "variables": ["q1", "m1"], "label": "Combo"}], "singles": []}
    r = client_memory.put(f"/materials/{mid}/grouping", json=body)
    assert r.status_code == 200
    combo = [q for q in r.json()["questions"]
             if q["kind"] == "multi" and set(q["variables"]) == {"q1", "m1"}]
    assert combo and combo[0]["text"] == "Combo"

    # Persisted (GET) and reflected in the question list (model reshaped server-side).
    ov = client_memory.get(f"/materials/{mid}/grouping").json()["override"]
    assert ov["groups"][0]["variables"] == ["q1", "m1"]
    ql = client_memory.get(f"/materials/{mid}/questions").json()["questions"]
    assert any(q["kind"] == "multi" and set(q["variables"]) == {"q1", "m1"} for q in ql)


def test_put_split_forces_singles(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    # synthetic auto-groups m1+m2 into one multi; splitting dissolves it.
    before = client_memory.get(f"/materials/{mid}/questions").json()["questions"]
    assert any(q["kind"] == "multi" for q in before)
    client_memory.put(f"/materials/{mid}/grouping", json={"groups": [], "singles": ["m1", "m2"]})
    after = client_memory.get(f"/materials/{mid}/questions").json()["questions"]
    assert not any(q["kind"] == "multi" for q in after)


def test_put_validation_422s(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    def put(groups, singles=None):
        return client_memory.put(f"/materials/{mid}/grouping",
                                 json={"groups": groups, "singles": singles or []})
    assert put([{"kind": "multi", "variables": ["q1"]}]).status_code == 422           # <2
    assert put([{"kind": "multi", "variables": ["q1", "ghost"]}]).status_code == 422   # unknown
    assert put([{"kind": "multi", "variables": ["q1", "age"]}]).status_code == 422     # scale
    assert put([{"kind": "multi", "variables": ["q1", "m1"]},
                {"kind": "multi", "variables": ["m1", "m2"]}]).status_code == 422       # double-assign


def test_group_member_dropped_from_singles(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    body = {"groups": [{"kind": "multi", "variables": ["q1", "m1"]}], "singles": ["m1", "m2"]}
    client_memory.put(f"/materials/{mid}/grouping", json=body)
    ov = client_memory.get(f"/materials/{mid}/grouping").json()["override"]
    assert "m1" not in ov["singles"]   # a group member can't also be a forced single
    assert "m2" in ov["singles"]


def test_variables_include_all_is_superset(client_memory, synthetic_bytes):
    mid = _case_material(client_memory, synthetic_bytes)
    base = client_memory.get(f"/materials/{mid}/variables").json()["variables"]
    allv = client_memory.get(f"/materials/{mid}/variables?include_all=true").json()["variables"]
    assert len(allv) >= len(base)
