"""Integration tests for the RENDER API (routes_render).

Covers:
  - POST /cases/{cid}/reports/{rid}/render            (orchestrated export)
  - GET  /cases/{cid}/reports/{rid}/preview.pdf|pptx  (stream artifacts)
  - render_output_dir(case_id, report_id)             (deterministic + sanitized)

The stacked-no-classifying 422 guard and the artifact-404-before-render behavior
are soffice-FREE (they raise before / independently of LibreOffice). The FULL
happy-path render (build_pptx → pptx_to_pdf → rasterize) is `@pytest.mark.export`
+ `require_soffice`.

`client_memory` is a real local-fs InMemoryDataHive; we drive the true product
flow: create case → upload material → create report → render.
"""
from __future__ import annotations

import json
import shutil

import pytest

from reportbuilder.api.routes_render import render_output_dir
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    report_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report_json(chart_type: str, *, classifying_var=None,
                      question_ref: str = "q1") -> dict:
    """A valid single-chart report definition as a JSON-ready dict."""
    spec = ChartSpec(
        question_ref=question_ref, chart_type=chart_type, statistic="pct",
        classifying_var=classifying_var, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(),
    )
    report = Report(name="R", render_mode="native", template_ref="",
                    charts=(spec,))
    return json.loads(report_to_json(report))


def _seed_case_material_report(client, chart_type: str, *,
                               classifying_var=None) -> tuple[str, str, str]:
    """Create a case, upload the synthetic SAV, and create a report with one
    chart. Returns (case_id, report_id, material_id)."""
    from reportbuilder.testing.fixtures import synthetic_sav_bytes

    cid = client.post("/cases", json={"name": "C"}).json()["case_id"]
    up = client.post(
        f"/cases/{cid}/materials",
        files={"file": ("t.sav", synthetic_sav_bytes(),
                        "application/octet-stream")},
    ).json()
    mid = up["material_id"]
    rid = client.post(
        f"/cases/{cid}/reports",
        json=_make_report_json(chart_type, classifying_var=classifying_var),
    ).json()["report_id"]
    return cid, rid, mid


# ---------------------------------------------------------------------------
# render_output_dir helper
# ---------------------------------------------------------------------------


def test_render_output_dir_is_deterministic():
    a = render_output_dir("case-1", "report-1")
    b = render_output_dir("case-1", "report-1")
    assert a == b
    assert a.name == "report-1" and a.parent.name == "case-1"


def test_render_output_dir_sanitizes_path_traversal():
    """Traversal segments in ids must not escape the base dir."""
    d = render_output_dir("../evil", "../../etc")
    assert ".." not in d.parts
    # Only alnum/-/_ survive sanitisation, so a bare-dots component collapses.
    assert d.parent.name == "evil"
    # The whole path stays under the nsight-render base.
    assert "nsight-render" in d.parts


# ---------------------------------------------------------------------------
# Artifact streaming — 404 before any render exists
# ---------------------------------------------------------------------------


def test_preview_pdf_404_before_render(client_memory):
    cid, rid, _mid = _seed_case_material_report(client_memory, "vertical_bar")
    # render_output_dir is a deterministic dir in a shared temp root; a prior
    # export run may have left artifacts under the reused (case-1/report-1) ids,
    # so clear it to genuinely assert the pre-render state.
    shutil.rmtree(render_output_dir(cid, rid), ignore_errors=True)
    r = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pdf")
    assert r.status_code == 404


def test_preview_pptx_404_before_render(client_memory):
    cid, rid, _mid = _seed_case_material_report(client_memory, "vertical_bar")
    shutil.rmtree(render_output_dir(cid, rid), ignore_errors=True)
    r = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pptx")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Stacked-no-classifying guard on render (soffice-free — raises before build)
# ---------------------------------------------------------------------------


def test_render_stacked_without_classifying_var_not_blocked(client_memory):
    """A non-battery stacked chart with no classifying variable is a valid
    total-only distribution — the render must NOT be rejected with a
    'classifying variable' 422 (holds with or without LibreOffice)."""
    cid, rid, mid = _seed_case_material_report(
        client_memory, "stacked_vertical_bar", classifying_var=None,
    )
    r = client_memory.post(
        f"/cases/{cid}/reports/{rid}/render",
        json={"material_id": mid, "view": "slides"},
    )
    assert not (r.status_code == 422
                and "classifying variable" in r.json().get("detail", "").lower()), (
        f"total-only stacked render must no longer be blocked: {r.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Full happy-path render (needs real LibreOffice) — export-gated
# ---------------------------------------------------------------------------


@pytest.mark.export
def test_render_happy_path_returns_artifacts(client_memory, require_soffice):
    """A valid report renders end-to-end: response carries pptx/pdf/preview/
    pdf_url, and the streamed preview.pdf/pptx then resolve (200)."""
    cid, rid, mid = _seed_case_material_report(client_memory, "vertical_bar")
    r = client_memory.post(
        f"/cases/{cid}/reports/{rid}/render",
        json={"material_id": mid, "view": "slides"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"pptx", "pdf", "preview", "pdf_url"}
    assert body["pdf_url"] == f"/cases/{cid}/reports/{rid}/preview.pdf"
    assert isinstance(body["preview"], list) and body["preview"]

    # Artifacts are now fetchable.
    pdf = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"

    pptx = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pptx")
    assert pptx.status_code == 200
    # PPTX is a zip container → starts with the "PK" local-file-header magic.
    assert pptx.content[:2] == b"PK"
