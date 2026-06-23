"""Three-layer fidelity gate tests (design §10, REQ-C-20).

Layer 1+2: native mode — pptx chart-data and pdf data-labels match SeriesResult.
Layer 3:   image mode — engine.compute output matches SeriesResult (identity check, §C4).
"""
from __future__ import annotations

import dataclasses
import shutil

import pytest

from reportbuilder.export.fidelity_gate import run_fidelity_gate
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, Report, SortSpec
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fixtures import (
    known_series,
    one_chart_report,
    tiny_model_and_data,
)
from reportbuilder.stats.series import Cell

pytestmark = pytest.mark.skipif(
    shutil.which("soffice") is None,
    reason="LibreOffice required",
)


# ---------------------------------------------------------------------------
# Test 1: native mode — gate passes with correct series
# ---------------------------------------------------------------------------

def test_gate_passes_native(tmp_path):
    """run_fidelity_gate does NOT raise when series matches the rendered pptx/pdf."""
    model, data = tiny_model_and_data()
    report = one_chart_report()
    pptx = build_pptx(report, model, data, str(tmp_path / "r.pptx"))
    pdf = pptx_to_pdf(pptx, str(tmp_path))
    # Should not raise — known_series() == Yes60/No40 which matches what q1 renders
    run_fidelity_gate(report, model, data, pptx, pdf, known_series())


# ---------------------------------------------------------------------------
# Test 2: native mode — gate raises on tampered series (drift guard)
# ---------------------------------------------------------------------------

def test_gate_fails_on_drift(tmp_path):
    """run_fidelity_gate raises AssertionError when series doesn't match pptx/pdf."""
    model, data = tiny_model_and_data()
    report = one_chart_report()
    pptx = build_pptx(report, model, data, str(tmp_path / "r.pptx"))
    pdf = pptx_to_pdf(pptx, str(tmp_path))

    # Tamper: bump every Cell's pct by +50, and bump base_n
    # pptx/pdf carry 60/40; tampered series expects 110/90 — not present → raises
    original = known_series()
    tampered_cells = {
        key: dataclasses.replace(cell, pct=(cell.pct or 0.0) + 50.0)
        for key, cell in original.cells.items()
    }
    tampered = dataclasses.replace(
        original,
        cells=tampered_cells,
        base_n={"Total": original.base_n["Total"] + 50},
    )

    with pytest.raises(AssertionError):
        run_fidelity_gate(report, model, data, pptx, pdf, tampered)


# ---------------------------------------------------------------------------
# Test 3: image mode — layer 3 passes with correct series
# ---------------------------------------------------------------------------

def test_gate_image_layer3_passes(tmp_path):
    """Image mode: run_fidelity_gate does NOT raise when engine.compute matches known_series."""
    model, data = tiny_model_and_data()
    image_report = dataclasses.replace(one_chart_report(), render_mode="image")
    pptx = build_pptx(image_report, model, data, str(tmp_path / "r.pptx"))
    # Image path doesn't need the pdf — pass pdf_path=None
    run_fidelity_gate(image_report, model, data, pptx, None, known_series())


# ---------------------------------------------------------------------------
# Test 4: image mode — layer 3 raises on tampered series
# ---------------------------------------------------------------------------

def test_gate_image_layer3_fails_on_wrong_series(tmp_path):
    """Image mode: run_fidelity_gate raises AssertionError when series doesn't match recomputed."""
    model, data = tiny_model_and_data()
    image_report = dataclasses.replace(one_chart_report(), render_mode="image")
    pptx = build_pptx(image_report, model, data, str(tmp_path / "r.pptx"))

    # Tamper series — same approach as test 2
    original = known_series()
    tampered_cells = {
        key: dataclasses.replace(cell, pct=(cell.pct or 0.0) + 50.0)
        for key, cell in original.cells.items()
    }
    tampered = dataclasses.replace(
        original,
        cells=tampered_cells,
        base_n={"Total": original.base_n["Total"] + 50},
    )

    with pytest.raises(AssertionError):
        run_fidelity_gate(image_report, model, data, pptx, None, tampered)


# ---------------------------------------------------------------------------
# Test 5: image mode — layer 3 passes for non-core summary stat (median) (REQ-C-20)
# ---------------------------------------------------------------------------

def test_gate_image_layer3_median_passes(tmp_path):
    """Layer-3 fidelity gate passes for statistic='median' over a scale variable.

    This is the regression test for the missed getattr() call site in
    fidelity_gate.py:35 — before the fix, getattr(cell, 'median') raised
    AttributeError because median is stored in cell.extra, not as a named field.
    After the fix, cell.value('median') is used and the gate passes. (REQ-C-20)
    """
    model, data = tiny_model_and_data()
    # age column: [30, 40, 50, 60, 70] -> median = 50.0
    median_spec = ChartSpec(
        question_ref="age",
        chart_type="vertical_bar",
        statistic="median",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="slot1",
        elements=ElementToggles(),
    )
    image_report = Report(
        name="MedianImageTest",
        render_mode="image",
        template_ref="t.pptx",
        charts=(median_spec,),
    )
    pptx = build_pptx(image_report, model, data, str(tmp_path / "r.pptx"))

    # Build the series that would have fed the builder
    age_q = model.question("age")
    series = compute(age_q, median_spec, data, model)

    # Should NOT raise — cell.value('median') routes through extra, not getattr
    run_fidelity_gate(image_report, model, data, pptx, None, series)


# ---------------------------------------------------------------------------
# Test 6: image mode — layer 3 raises on tampered median series (REQ-C-20)
# ---------------------------------------------------------------------------

def test_gate_image_layer3_median_fails_on_tamper(tmp_path):
    """Layer-3 fidelity gate raises AssertionError when the median series is tampered. (REQ-C-20)"""
    model, data = tiny_model_and_data()
    median_spec = ChartSpec(
        question_ref="age",
        chart_type="vertical_bar",
        statistic="median",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="slot1",
        elements=ElementToggles(),
    )
    image_report = Report(
        name="MedianImageTamper",
        render_mode="image",
        template_ref="t.pptx",
        charts=(median_spec,),
    )
    pptx = build_pptx(image_report, model, data, str(tmp_path / "r.pptx"))

    age_q = model.question("age")
    original = compute(age_q, median_spec, data, model)

    # Tamper: replace the median extra value with an incorrect one (+999)
    tampered_cells = {
        key: dataclasses.replace(cell, extra=tuple(
            (k, (v or 0.0) + 999.0) for k, v in cell.extra
        ))
        for key, cell in original.cells.items()
    }
    tampered = dataclasses.replace(original, cells=tampered_cells)

    with pytest.raises(AssertionError):
        run_fidelity_gate(image_report, model, data, pptx, None, tampered)
