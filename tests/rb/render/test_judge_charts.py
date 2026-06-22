"""Claude-as-judge chart cleanliness tests (Task 5.17).

REQ-C-24, C-28b.

Each test:
  1. Builds a single-chart Report for the target chart type.
  2. Renders via render_report → saves PPTX.
  3. Converts PPTX → PDF via pptx_to_pdf (requires soffice).
  4. Rasterizes page 0 → PNG via pdf_page_to_png.
  5. Judges via judge_image(png, rubric_for("REQ-C-24"), requirement_id="REQ-C-24").
  6. Asserts verdict.passed.

Skip conditions (both applied to every test):
  - ``soffice`` not on PATH  →  pytest.mark.skipif
  - ``ANTHROPIC_API_KEY`` not set  →  pytest.mark.judge (collected but skipped)
"""
from __future__ import annotations

import os
import shutil

import pytest

from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import pdf_page_to_png
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.render.base import StyleSpec
from reportbuilder.render.deck import render_report
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.testing.rubrics import rubric_for

# ---------------------------------------------------------------------------
# Skip guards
# ---------------------------------------------------------------------------

_NO_SOFFICE = shutil.which("soffice") is None
_NO_API_KEY = not os.environ.get("ANTHROPIC_API_KEY")

_skip_soffice = pytest.mark.skipif(_NO_SOFFICE, reason="soffice not on PATH")
_skip_api_key = pytest.mark.skipif(_NO_API_KEY, reason="ANTHROPIC_API_KEY not set")


# ---------------------------------------------------------------------------
# Series builders
# ---------------------------------------------------------------------------

def _single_segment_series() -> SeriesResult:
    """4-category single-segment series (Total)."""
    cats = ("Option A", "Option B", "Option C", "Option D")
    cells = {
        ("Option A", "Total"): Cell(pct=45.0, count=45.0, mean=None),
        ("Option B", "Total"): Cell(pct=28.0, count=28.0, mean=None),
        ("Option C", "Total"): Cell(pct=17.0, count=17.0, mean=None),
        ("Option D", "Total"): Cell(pct=10.0, count=10.0, mean=None),
    }
    return SeriesResult(
        categories=cats,
        segments=("Total",),
        cells=cells,
        base_n={"Total": 100},
        statistic="pct",
    )


def _multi_segment_series() -> SeriesResult:
    """3-category × 2-segment + Total series."""
    cats = ("Cat1", "Cat2", "Cat3")
    segs = ("SegA", "SegB", "Total")
    cells = {
        ("Cat1", "SegA"): Cell(pct=70.0, count=70.0, mean=None),
        ("Cat2", "SegA"): Cell(pct=50.0, count=50.0, mean=None),
        ("Cat3", "SegA"): Cell(pct=30.0, count=30.0, mean=None),
        ("Cat1", "SegB"): Cell(pct=40.0, count=40.0, mean=None),
        ("Cat2", "SegB"): Cell(pct=60.0, count=60.0, mean=None),
        ("Cat3", "SegB"): Cell(pct=20.0, count=20.0, mean=None),
        ("Cat1", "Total"): Cell(pct=55.0, count=55.0, mean=None),
        ("Cat2", "Total"): Cell(pct=55.0, count=55.0, mean=None),
        ("Cat3", "Total"): Cell(pct=25.0, count=25.0, mean=None),
    }
    return SeriesResult(
        categories=cats,
        segments=segs,
        cells=cells,
        base_n={"SegA": 100, "SegB": 100, "Total": 200},
        statistic="pct",
    )


def _combo_series() -> SeriesResult:
    """2-segment series for image-mode combo (bars + line)."""
    cats = ("Q1", "Q2", "Q3", "Q4")
    cells = {
        ("Q1", "Revenue"): Cell(pct=25.0, count=250.0, mean=None),
        ("Q2", "Revenue"): Cell(pct=30.0, count=300.0, mean=None),
        ("Q3", "Revenue"): Cell(pct=28.0, count=280.0, mean=None),
        ("Q4", "Revenue"): Cell(pct=35.0, count=350.0, mean=None),
        ("Q1", "Growth"): Cell(pct=5.0, count=50.0, mean=None),
        ("Q2", "Growth"): Cell(pct=20.0, count=200.0, mean=None),
        ("Q3", "Growth"): Cell(pct=-7.0, count=-70.0, mean=None),
        ("Q4", "Growth"): Cell(pct=25.0, count=250.0, mean=None),
    }
    return SeriesResult(
        categories=cats,
        segments=("Revenue", "Growth"),
        cells=cells,
        base_n={"Revenue": 1000, "Growth": 1000},
        statistic="pct",
    )


# ---------------------------------------------------------------------------
# Render helper
# ---------------------------------------------------------------------------

def _make_chart_spec(chart_type: str, scatter_xy=None) -> ChartSpec:
    return ChartSpec(
        question_ref="q1",
        chart_type=chart_type,
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="slot1",
        elements=ElementToggles(
            title=True,
            legend=True,
            n=True,
            axis_names=True,
            filter_var=False,
            data_labels=True,
        ),
        scatter_xy=scatter_xy,
    )


def _render_chart_to_png(
    chart_type: str,
    series: SeriesResult,
    tmp_path,
    *,
    render_mode: str = "native",
    scatter_xy=None,
    title: str = "Test Chart",
) -> str:
    """Build a single-chart Report, render to PPTX, convert to PDF, rasterize page 0.

    Returns the absolute path to the resulting PNG file.
    """
    spec = _make_chart_spec(chart_type, scatter_xy=scatter_xy)
    report = Report(
        name=f"judge-{chart_type}",
        render_mode=render_mode,
        template_ref="t.pptx",
        charts=(spec,),
    )
    style = StyleSpec()
    series_by_ref = {"q1": series}
    titles = {"q1": title}

    prs = render_report(report, series_by_ref, style, titles)

    pptx_path = str(tmp_path / f"{chart_type}.pptx")
    prs.save(pptx_path)

    pdf_dir = str(tmp_path / "pdf")
    pdf_path = pptx_to_pdf(pptx_path, pdf_dir)

    png_path = str(tmp_path / f"{chart_type}.png")
    pdf_page_to_png(pdf_path, 0, png_path, resolution=150)

    return png_path


# ---------------------------------------------------------------------------
# Judge tests
# ---------------------------------------------------------------------------

@pytest.mark.judge
@_skip_soffice
@_skip_api_key
def test_judge_native_vertical_bar_clean(tmp_path):
    """Native vertical_bar renders as a clean, legible chart (REQ-C-24)."""
    series = _single_segment_series()
    png = _render_chart_to_png(
        "vertical_bar", series, tmp_path,
        render_mode="native",
        title="Vertical Bar Chart",
    )
    from reportbuilder.testing.judge import judge_image
    verdict = judge_image(
        png,
        rubric_for("REQ-C-24"),
        requirement_id="REQ-C-24",
        extra_context="Chart type under test: native vertical bar chart (clustered columns).",
    )
    assert verdict.passed is True, verdict.reasoning


@pytest.mark.judge
@_skip_soffice
@_skip_api_key
def test_judge_native_stacked_horizontal_bar_clean(tmp_path):
    """Native stacked_horizontal_bar (multi-segment) renders clean (REQ-C-24)."""
    series = _multi_segment_series()
    png = _render_chart_to_png(
        "stacked_horizontal_bar", series, tmp_path,
        render_mode="native",
        title="Stacked Horizontal Bar Chart",
    )
    from reportbuilder.testing.judge import judge_image
    verdict = judge_image(
        png,
        rubric_for("REQ-C-24"),
        requirement_id="REQ-C-24",
        extra_context="Chart type under test: native stacked horizontal bar chart with 2 data series plus Total.",
    )
    assert verdict.passed is True, verdict.reasoning


@pytest.mark.judge
@_skip_soffice
@_skip_api_key
def test_judge_native_radar_clean(tmp_path):
    """Native radar (multi-segment) renders clean (REQ-C-24)."""
    series = _multi_segment_series()
    png = _render_chart_to_png(
        "radar", series, tmp_path,
        render_mode="native",
        title="Radar Chart",
    )
    from reportbuilder.testing.judge import judge_image
    verdict = judge_image(
        png,
        rubric_for("REQ-C-24"),
        requirement_id="REQ-C-24",
        extra_context="Chart type under test: native radar (spider/web) chart with 2 data series plus Total.",
    )
    assert verdict.passed is True, verdict.reasoning


@pytest.mark.judge
@_skip_soffice
@_skip_api_key
def test_judge_native_funnel_clean(tmp_path):
    """Native funnel renders clean (REQ-C-24)."""
    series = _single_segment_series()
    png = _render_chart_to_png(
        "funnel", series, tmp_path,
        render_mode="native",
        title="Funnel Chart",
    )
    from reportbuilder.testing.judge import judge_image
    verdict = judge_image(
        png,
        rubric_for("REQ-C-24"),
        requirement_id="REQ-C-24",
        extra_context="Chart type under test: native funnel chart (single series).",
    )
    assert verdict.passed is True, verdict.reasoning


@pytest.mark.judge
@_skip_soffice
@_skip_api_key
def test_judge_image_combo_clean(tmp_path):
    """Image-mode combo chart (bars + line, 2 segments) renders clean (REQ-C-24)."""
    series = _combo_series()
    png = _render_chart_to_png(
        "combo", series, tmp_path,
        render_mode="image",
        title="Combo Chart (Bars + Line)",
    )
    from reportbuilder.testing.judge import judge_image
    verdict = judge_image(
        png,
        rubric_for("REQ-C-24"),
        requirement_id="REQ-C-24",
        extra_context="Chart type under test: image-mode combo chart (bars on primary axis, line on secondary axis, 2 segments).",
    )
    assert verdict.passed is True, verdict.reasoning
