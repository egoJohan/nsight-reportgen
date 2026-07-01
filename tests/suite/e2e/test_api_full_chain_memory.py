"""The whole API driven end-to-end via the in-memory client (`client_memory`).

Soffice-free parts always run: create case → upload synthetic SAV → list
questions (q1 present) → create report referencing q1 → GET round-trip →
duplicate (new id) → delete. The render step + preview.pdf streaming is gated
with `@pytest.mark.export` + `require_soffice` (needs LibreOffice).
"""
from __future__ import annotations

import json

import pytest

from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    report_to_json,
)
from reportbuilder.testing.fixtures import synthetic_sav_bytes


def _report_json(question_ref: str = "q1") -> dict:
    spec = ChartSpec(
        question_ref=question_ref, chart_type="vertical_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="slot1",
        elements=ElementToggles(),
    )
    report = Report(name="api-chain", render_mode="native", template_ref="t.pptx",
                    charts=(spec,))
    return json.loads(report_to_json(report))


def _seed(client) -> tuple[str, str]:
    """Create a case and upload the synthetic SAV. Returns (case_id, material_id)."""
    cid = client.post("/cases", json={"name": "api-chain"}).json()["case_id"]
    up = client.post(
        f"/cases/{cid}/materials",
        files={"file": ("synthetic.sav", synthetic_sav_bytes(),
                        "application/octet-stream")},
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["question_count"] > 0
    return cid, body["material_id"]


def test_full_crud_chain_soffice_free(client_memory):
    """Case → material → questions → report create/get/duplicate/delete, no soffice."""
    cid, mid = _seed(client_memory)

    # List questions — q1 must be present.
    q = client_memory.get(f"/materials/{mid}/questions")
    assert q.status_code == 200
    qids = {row["qid"] for row in q.json()["questions"]}
    assert "q1" in qids

    # Create a report referencing q1.
    created = client_memory.post(f"/cases/{cid}/reports", json=_report_json("q1"))
    assert created.status_code == 200, created.text
    rid = created.json()["report_id"]
    assert isinstance(rid, str) and rid

    # GET it back — round-trips.
    got = client_memory.get(f"/cases/{cid}/reports/{rid}")
    assert got.status_code == 200
    assert got.json()["name"] == "api-chain"

    # Duplicate — new id, original untouched.
    dup = client_memory.post(
        f"/cases/{cid}/reports/{rid}/duplicate", json={"name": "api-chain copy"}
    )
    assert dup.status_code == 200
    new_id = dup.json()["report_id"]
    assert new_id != rid
    assert client_memory.get(f"/cases/{cid}/reports/{new_id}").json()["name"] == "api-chain copy"
    assert client_memory.get(f"/cases/{cid}/reports/{rid}").json()["name"] == "api-chain"

    # Delete the original.
    dele = client_memory.delete(f"/cases/{cid}/reports/{rid}")
    assert dele.status_code == 200
    assert client_memory.get(f"/cases/{cid}/reports/{rid}").status_code == 404


@pytest.mark.export
def test_full_chain_render_and_preview(client_memory, require_soffice):
    """The render step + preview.pdf streaming (needs LibreOffice)."""
    cid, mid = _seed(client_memory)
    rid = client_memory.post(
        f"/cases/{cid}/reports", json=_report_json("q1")
    ).json()["report_id"]

    r = client_memory.post(
        f"/cases/{cid}/reports/{rid}/render",
        json={"material_id": mid, "view": "slides"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.keys()) >= {"pptx", "pdf", "preview", "pdf_url"}
    assert body["pdf_url"] == f"/cases/{cid}/reports/{rid}/preview.pdf"

    pdf = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pdf")
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"
