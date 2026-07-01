"""Full data→export pipeline: synthetic SAV → build_pptx → pptx_to_pdf.

`@pytest.mark.export` + `require_soffice`: gated on LibreOffice being present.
Builds a 2-chart deck in both render modes and asserts:
  * the PDF page count equals the number of chart specs, and
  * for NATIVE mode, a known synthetic value survives into the PDF text layer
    (q1 pct == 60.0, age mean == 50.0). Image-mode PDFs are rasterised PNGs with
    no text layer, so only the page count is checked there (see
    tests/rb/e2e/test_pipeline_synthetic.py note C).
"""
from __future__ import annotations

import os

import pytest

from reportbuilder.export.pdf_convert import pdf_page_count, pptx_to_pdf
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fidelity import numbers_from_pdf
from reportbuilder.testing.fixtures import synthetic_sav

pytestmark = pytest.mark.export


def _chart_spec(question_ref: str, slot: str, statistic: str = "pct") -> ChartSpec:
    return ChartSpec(
        question_ref=question_ref,
        chart_type="vertical_bar",
        statistic=statistic,
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot=slot,
        elements=ElementToggles(),
    )


@pytest.mark.parametrize("mode", ["native", "image"])
def test_pipeline_export_to_pdf(mode, tmp_path, require_soffice):
    """2-chart deck (q1 pct + age mean) → PPTX → PDF: page count == chart count;
    native mode additionally proves data values survive into the PDF text layer."""
    df, model = read_sav(synthetic_sav(tmp_path))
    model = enrich_model(model)

    age_q = next(q for q in model.questions if q.variables == ("age",))

    charts = (
        _chart_spec("q1", "slot1", statistic="pct"),
        _chart_spec(age_q.qid, "slot2", statistic="mean"),
    )
    report = Report(
        name="synthetic-export-e2e",
        render_mode=mode,
        template_ref="t.pptx",
        charts=charts,
    )

    pptx = build_pptx(report, model, df, str(tmp_path / "deck.pptx"))
    assert os.path.isfile(pptx), f"build_pptx did not produce a file: {pptx}"

    pdf = pptx_to_pdf(pptx, str(tmp_path))
    assert os.path.isfile(pdf), f"pptx_to_pdf did not produce a file: {pdf}"

    # Page count == number of chart specs.
    assert pdf_page_count(pdf) == len(charts), (
        f"expected {len(charts)} PDF pages, got {pdf_page_count(pdf)}"
    )

    if mode == "native":
        # A known value from the synthetic data must appear in the PDF text layer.
        # q1 "Yes" pct == 60.0; age mean of [30,40,50,60,70] == 50.0.
        series_q1 = compute(model.question("q1"), charts[0], df, model)
        yes_pct = series_q1.cells[("Yes", "Total")].pct
        assert abs(yes_pct - 60.0) < 0.01, f"unexpected q1 pct: {yes_pct}"

        nums = numbers_from_pdf(pdf)
        assert any(abs(60.0 - got) <= 1.0 for got in nums), (
            f"q1 value 60.0 not found in native PDF numbers: {nums}"
        )
        assert any(abs(50.0 - got) <= 1.0 for got in nums), (
            f"age mean 50.0 not found in native PDF numbers: {nums}"
        )
    # Image mode: page count verified; rasterised PNGs carry no text layer.
