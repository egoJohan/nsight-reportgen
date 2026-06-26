"""Full REST-surface E2E via an in-memory FakeHive client.

Drives the complete API surface — cases → material upload → questions →
report CRUD → duplicate → render → PDF — with no live datahive dependency.

Requirements covered: REQ-C-03, REQ-C-04, REQ-C-05, REQ-C-08, REQ-C-09,
REQ-C-19, REQ-C-21, REQ-C-22.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    report_from_json,
    report_to_json,
)
from reportbuilder.testing.fixtures import synthetic_sav_bytes

# ---------------------------------------------------------------------------
# In-memory fake DataHiveClient
# ---------------------------------------------------------------------------


class FakeHive:
    """Fully in-memory implementation of DataHiveClient for E2E tests.

    Uses plain dicts for storage; generates sequential ids prefixed by type.
    All 8 DataHiveClient methods are implemented; aggregate raises
    NotImplementedError to match the real client's behaviour.
    """

    def __init__(self):
        self.cases: dict[str, dict] = {}
        self.materials: dict[str, dict] = {}
        self.reports: dict[str, str] = {}  # report_id -> report_json
        self._n: int = 0

    def _id(self, prefix: str) -> str:
        self._n += 1
        return f"{prefix}{self._n}"

    def create_case(self, name: str) -> str:
        cid = self._id("case-")
        self.cases[cid] = {"id": cid, "name": name}
        return cid

    def list_cases(self) -> list[dict]:
        return list(self.cases.values())

    def attach_material(
        self,
        case_id: str,
        name: str,
        sav_bytes: bytes,
        codebook_summary: str,
    ) -> str:
        mid = self._id("mat-")
        self.materials[mid] = {"case": case_id, "name": name, "bytes": sav_bytes}
        return mid

    def get_material(self, material_id: str) -> bytes:
        return self.materials[material_id]["bytes"]

    def save_report(
        self,
        case_id: str,
        report_id: str | None,
        report_json: str,
        readable: str,
    ) -> str:
        rid = report_id or self._id("rep-")
        self.reports[rid] = report_json
        return rid

    def load_report(self, case_id: str, report_doc_id: str) -> str:
        return self.reports[report_doc_id]

    def delete_report(self, case_id: str, report_doc_id: str) -> None:
        self.reports.pop(report_doc_id, None)

    def aggregate(self, *args, **kwargs):
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Test — full API chain
# ---------------------------------------------------------------------------


@pytest.mark.integration
def test_api_full_chain(tmp_path):
    """Drive the entire REST surface end-to-end with a fake DataHiveClient.

    Steps executed:
      1. POST /cases — create a case (REQ-C-03).
      2. POST /cases/{case_id}/materials — upload synthetic .sav (REQ-C-04).
      3. GET /materials/{material_id}/questions — browse questions (REQ-C-05).
      4. POST /cases/{case_id}/reports — create a 1-chart report (REQ-C-08).
      5. GET /cases/{case_id}/reports/{report_id} — exact round-trip (REQ-C-08).
      6. POST .../duplicate — new id + new name (REQ-C-09).
      7. POST .../render — PPTX + PDF + preview produced (REQ-C-19/21/22).
         Step 7 is skipped if soffice is absent; steps 1-6 always run.

    REQ-C-03, REQ-C-04, REQ-C-05, REQ-C-08, REQ-C-09, REQ-C-19, REQ-C-21, REQ-C-22.
    """
    hive = FakeHive()
    app = create_app(client=hive)
    tc = TestClient(app)

    # ------------------------------------------------------------------
    # Step 1: POST /cases  (REQ-C-03)
    # ------------------------------------------------------------------
    resp = tc.post("/cases", json={"name": "E2E"})
    assert resp.status_code in (200, 201), resp.text
    case_id = resp.json()["case_id"]
    assert case_id  # non-empty

    # ------------------------------------------------------------------
    # Step 2: POST /cases/{case_id}/materials  (REQ-C-04)
    # ------------------------------------------------------------------
    sav_bytes = synthetic_sav_bytes()
    resp = tc.post(
        f"/cases/{case_id}/materials",
        files={"file": ("synthetic.sav", sav_bytes, "application/octet-stream")},
    )
    assert resp.status_code in (200, 201), resp.text
    data = resp.json()
    material_id = data["material_id"]
    assert data["question_count"] >= 1, (
        f"Expected at least 1 question; got {data['question_count']}"
    )

    # ------------------------------------------------------------------
    # Step 3: GET /materials/{material_id}/questions  (REQ-C-05)
    # ------------------------------------------------------------------
    resp = tc.get(f"/materials/{material_id}/questions")
    assert resp.status_code == 200, resp.text
    questions = resp.json()["questions"]
    assert len(questions) >= 1, "Expected at least 1 question from the material"

    # Pick q1 (single-choice) — safest qid after auto-grouping of the synthetic .sav
    q1 = next((q for q in questions if q["qid"] == "q1"), questions[0])
    qid = q1["qid"]

    # ------------------------------------------------------------------
    # Step 4: POST /cases/{case_id}/reports  (REQ-C-08)
    # ------------------------------------------------------------------
    original_report = Report(
        name="E2E Report",
        render_mode="native",
        template_ref="t.pptx",
        charts=(
            ChartSpec(
                question_ref=qid,
                chart_type="vertical_bar",
                statistic="pct",
                classifying_var=None,
                number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"),
                template_slot="s1",
                elements=ElementToggles(),
            ),
        ),
    )
    report_body = json.loads(report_to_json(original_report))

    resp = tc.post(f"/cases/{case_id}/reports", json=report_body)
    assert resp.status_code in (200, 201), resp.text
    report_id = resp.json()["report_id"]
    assert report_id

    # ------------------------------------------------------------------
    # Step 5: GET /cases/{case_id}/reports/{report_id} — exact round-trip  (REQ-C-08)
    # ------------------------------------------------------------------
    resp = tc.get(f"/cases/{case_id}/reports/{report_id}")
    assert resp.status_code == 200, resp.text

    loaded = report_from_json(resp.json())
    assert loaded == original_report, (
        "GET response does not round-trip to the original Report"
    )

    # ------------------------------------------------------------------
    # Step 6: POST .../duplicate  (REQ-C-09)
    # ------------------------------------------------------------------
    resp = tc.post(
        f"/cases/{case_id}/reports/{report_id}/duplicate",
        json={"name": "E2E copy"},
    )
    assert resp.status_code in (200, 201), resp.text
    dup_id = resp.json()["report_id"]
    assert dup_id != report_id, "Duplicate must have a different report_id"

    # Verify the stored duplicate has name "E2E copy"
    dup_json = hive.load_report(case_id, dup_id)
    assert report_from_json(dup_json).name == "E2E copy", (
        f"Duplicate report name should be 'E2E copy'; stored JSON: {dup_json}"
    )

    # ------------------------------------------------------------------
    # Step 7: POST .../render  (REQ-C-19, REQ-C-21, REQ-C-22)
    # Skipped if soffice is absent — steps 1-6 above always run.
    # ------------------------------------------------------------------
    if shutil.which("soffice") is None:
        pytest.skip("soffice not on PATH — render step skipped")

    resp = tc.post(
        f"/cases/{case_id}/reports/{report_id}/render",
        json={"material_id": material_id},
    )
    assert resp.status_code == 200, resp.text
    result = resp.json()

    assert "pptx" in result, "Render response missing 'pptx'"
    assert "pdf" in result, "Render response missing 'pdf'"
    assert "preview" in result, "Render response missing 'preview'"
    assert isinstance(result["preview"], list) and len(result["preview"]) > 0, (
        "Render 'preview' should be a non-empty list of PNG paths"
    )

    # The PDF file must exist on disk (REQ-C-21)
    assert os.path.isfile(result["pdf"]), (
        f"Rendered PDF not found on disk: {result['pdf']}"
    )
