"""Tests for render router: orchestrate_render chain and POST /cases/.../render.
(REQ-C-19, REQ-C-21, REQ-C-22)
"""
from __future__ import annotations

import os
from unittest.mock import Mock, patch

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
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

_ARTIFACTS = {
    "pptx": "/t/deck.pptx",
    "pdf": "/t/deck.pdf",
    "preview": ["/t/p1.png"],
}


def _make_mock_client() -> Mock:
    return Mock()


def _make_small_report() -> Report:
    chart = ChartSpec(
        question_ref="q1",
        chart_type="bar",
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="slot-A",
        elements=ElementToggles(),
    )
    return Report(
        name="Mini Report",
        render_mode="native",
        template_ref="tpl-1",
        charts=(chart,),
    )


def _make_small_model() -> QuestionModel:
    var = Variable(
        name="q1_var",
        label="Question 1",
        measurement="categorical",
        value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(0.0, "No")),
        missing_values=frozenset(),
    )
    question = Question(qid="q1", kind="single", variables=("q1_var",), text="Question 1")
    return QuestionModel(variables={"q1_var": var}, questions=[question])


# ---------------------------------------------------------------------------
# Test 1 — Route returns artifacts dict (REQ-C-19, REQ-C-21, REQ-C-22)
# ---------------------------------------------------------------------------


def test_route_returns_artifacts() -> None:
    """POST /cases/.../render returns the artifact dict from orchestrate_render.
    (REQ-C-19, REQ-C-21, REQ-C-22)"""
    mock_client = _make_mock_client()
    app = create_app(client=mock_client)
    http = TestClient(app)

    with patch("reportbuilder.api.routes_render.orchestrate_render") as mock_orch:
        mock_orch.return_value = dict(_ARTIFACTS)

        resp = http.post(
            "/cases/case-1/reports/rep-1/render",
            json={"material_id": "mat-1"},
        )

    assert resp.status_code == 200
    assert resp.json() == {**_ARTIFACTS, "pdf_url": "/cases/case-1/reports/rep-1/preview.pdf"}

    mock_orch.assert_called_once()
    call_args = mock_orch.call_args
    # positional: case_id, report_id, material_id, client
    assert call_args[0][0] == "case-1"
    assert call_args[0][1] == "rep-1"
    assert call_args[0][2] == "mat-1"
    # keyword: view defaults to "slides"
    assert call_args[1]["view"] == "slides"


# ---------------------------------------------------------------------------
# Test 2 — view=pages is forwarded to orchestrate_render (REQ-C-19)
# ---------------------------------------------------------------------------


def test_route_forwards_view_pages() -> None:
    """POST body with view=pages causes orchestrate_render to receive view='pages'.
    (REQ-C-19)"""
    mock_client = _make_mock_client()
    app = create_app(client=mock_client)
    http = TestClient(app)

    with patch("reportbuilder.api.routes_render.orchestrate_render") as mock_orch:
        mock_orch.return_value = dict(_ARTIFACTS)

        resp = http.post(
            "/cases/case-2/reports/rep-2/render",
            json={"material_id": "mat-1", "view": "pages"},
        )

    assert resp.status_code == 200
    mock_orch.assert_called_once()
    assert mock_orch.call_args[1]["view"] == "pages"


# ---------------------------------------------------------------------------
# Test 3 — orchestrate_render wiring without LibreOffice (REQ-C-19, REQ-C-21, REQ-C-22)
# ---------------------------------------------------------------------------


def test_orchestrate_render_wiring() -> None:
    """Call orchestrate_render directly with mocked heavy deps.
    Verifies the chain: read_sav -> build_pptx -> pptx_to_pdf -> slide_view.
    No LibreOffice or real .sav required.
    (REQ-C-19, REQ-C-21, REQ-C-22)"""
    from reportbuilder.api.routes_render import orchestrate_render

    small_report = _make_small_report()
    small_model = _make_small_model()
    fake_df = pd.DataFrame({"q1_var": [1.0, 0.0, 1.0]})

    mock_client = _make_mock_client()
    mock_client.load_report.return_value = report_to_json(small_report)
    mock_client.get_material.return_value = b"x"

    # build_pptx / pptx_to_pdf now write UNIQUE work files that the orchestrator
    # atomically publishes (os.replace) to canonical deck.pptx/deck.pdf, so the
    # mocks must actually create the files they stand in for.
    def _fake_build(report, model, df, path, cancel_check=None):
        with open(path, "w") as f:
            f.write("pptx")
        return path

    def _fake_pdf(pptx_path, out_dir):
        pdf = os.path.join(out_dir, "work.pdf")
        with open(pdf, "w") as f:
            f.write("pdf")
        return pdf

    with (
        patch("reportbuilder.api.routes_render.df_model_for_material") as mock_load,
        patch("reportbuilder.api.routes_render.build_pptx") as mock_build_pptx,
        patch("reportbuilder.api.routes_render.pptx_to_pdf") as mock_pptx_to_pdf,
        patch("reportbuilder.api.routes_render.slide_view") as mock_slide_view,
    ):
        mock_load.return_value = (fake_df, small_model)
        mock_build_pptx.side_effect = _fake_build
        mock_pptx_to_pdf.side_effect = _fake_pdf
        mock_slide_view.return_value = ["/t/p1.png"]

        result = orchestrate_render(
            "case-3", "rep-3", "mat-3", mock_client, view="slides"
        )

    # Atomic publish: canonical names, real files on disk, preview from slide_view.
    assert os.path.basename(result["pptx"]) == "deck.pptx"
    assert os.path.basename(result["pdf"]) == "deck.pdf"
    assert os.path.exists(result["pptx"]) and os.path.exists(result["pdf"])
    assert result["preview"] == ["/t/p1.png"]

    mock_client.load_report.assert_called_once_with("case-3", "rep-3")
    mock_load.assert_called_once()
    mock_build_pptx.assert_called_once()
    mock_pptx_to_pdf.assert_called_once()
    mock_slide_view.assert_called_once()


def test_orchestrate_render_cancels_before_pdf(tmp_path) -> None:
    """When cancel_check fires, orchestrate_render raises RenderCancelled and SKIPS the
    expensive LibreOffice PDF conversion — so a cancelled run stops promptly."""
    import pytest
    from reportbuilder.api.routes_render import orchestrate_render
    from reportbuilder.render.deck import RenderCancelled

    mock_client = _make_mock_client()
    mock_client.load_report.return_value = report_to_json(_make_small_report())
    mock_client.get_material.return_value = b"x"

    def _fake_build(report, model, df, path, cancel_check=None):
        open(path, "w").write("pptx")
        return path

    with (
        patch("reportbuilder.api.routes_render.df_model_for_material") as mock_load,
        patch("reportbuilder.api.routes_render.build_pptx") as mock_build,
        patch("reportbuilder.api.routes_render.pptx_to_pdf") as mock_pdf,
    ):
        mock_load.return_value = (pd.DataFrame({"q1_var": [1.0, 0.0]}), _make_small_model())
        mock_build.side_effect = _fake_build
        with pytest.raises(RenderCancelled):
            orchestrate_render("c", "r", "m", mock_client, view="slides",
                               out_dir=str(tmp_path), cancel_check=lambda: True)
        mock_pdf.assert_not_called()   # cancelled before the slow PDF step


# ---------------------------------------------------------------------------
# Test 4 — ValueError from build_pptx (e.g. scatter with null scatter_xy)
# becomes 422, not 500. (FIX-3)
# ---------------------------------------------------------------------------


def test_orchestrate_render_value_error_becomes_422() -> None:
    """A ValueError raised by build_pptx is surfaced as HTTP 422, not 500.
    This guards against scatter charts with a null scatter_xy crashing the
    render endpoint with an unhandled exception. (FIX-3)"""
    mock_client = _make_mock_client()
    app = create_app(client=mock_client)
    http = TestClient(app)

    small_report = _make_small_report()
    small_model = _make_small_model()
    fake_df = pd.DataFrame({"q1_var": [1.0, 0.0, 1.0]})

    mock_client.load_report.return_value = report_to_json(small_report)
    mock_client.get_material.return_value = b"x"

    with (
        patch("reportbuilder.api.routes_render.df_model_for_material") as mock_load,
        patch("reportbuilder.api.routes_render.build_pptx") as mock_build_pptx,
    ):
        mock_load.return_value = (fake_df, small_model)
        # Simulate scatter chart with null scatter_xy raising ValueError.
        mock_build_pptx.side_effect = ValueError("scatter chart requires scatter_xy")

        resp = http.post(
            "/cases/case-x/reports/rep-x/render",
            json={"material_id": "mat-x"},
        )

    assert resp.status_code == 422, (
        f"ValueError from build_pptx must map to 422, not {resp.status_code} (FIX-3)"
    )
    assert "scatter chart requires scatter_xy" in resp.json().get("detail", ""), (
        "422 detail must include the original ValueError message (FIX-3)"
    )
