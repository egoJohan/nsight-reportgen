"""GET /cases/{id}/materials and GET /cases/{id}/reports — server-side listing so
any user/device opening a case sees its material and reports (not browser-local).
"""
from __future__ import annotations

from reportbuilder.testing.fixtures import report_json_n_charts


def _new_case(client) -> str:
    return client.post("/cases", json={"name": "A"}).json()["case_id"]


def test_get_case_materials_lists_uploaded(client_memory, synthetic_bytes):
    cid = _new_case(client_memory)
    up = client_memory.post(
        f"/cases/{cid}/materials",
        files={"file": ("survey.sav", synthetic_bytes, "application/octet-stream")},
    )
    mid = up.json()["material_id"]

    r = client_memory.get(f"/cases/{cid}/materials")
    assert r.status_code == 200
    mats = r.json()["materials"]
    assert [m["material_id"] for m in mats] == [mid]
    assert mats[0]["name"] == "survey.sav"


def test_get_case_reports_lists_created(client_memory):
    cid = _new_case(client_memory)
    rid = client_memory.post(f"/cases/{cid}/reports", json=report_json_n_charts(1)).json()["report_id"]

    r = client_memory.get(f"/cases/{cid}/reports")
    assert r.status_code == 200
    reps = r.json()["reports"]
    assert [x["report_id"] for x in reps] == [rid]
    assert reps[0]["name"]


def test_case_materials_and_reports_are_scoped(client_memory, synthetic_bytes):
    a = _new_case(client_memory)
    b = _new_case(client_memory)
    client_memory.post(f"/cases/{a}/materials",
                       files={"file": ("a.sav", synthetic_bytes, "application/octet-stream")})
    client_memory.post(f"/cases/{a}/reports", json=report_json_n_charts(1))

    assert client_memory.get(f"/cases/{b}/materials").json()["materials"] == []
    assert client_memory.get(f"/cases/{b}/reports").json()["reports"] == []


def test_case_listing_empty_for_unknown_case(client_memory):
    assert client_memory.get("/cases/does-not-exist/materials").json()["materials"] == []
    assert client_memory.get("/cases/does-not-exist/reports").json()["reports"] == []
