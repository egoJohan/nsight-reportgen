"""TDD tests for native column chart builder (Task 1.2, R3 feasibility gate)."""
from __future__ import annotations
import io
import pytest
from pptx import Presentation
from pptx.oxml.ns import qn
from pptx.util import Inches
from pptx.enum.shapes import MSO_SHAPE_TYPE

from reportbuilder.render.base import Slot
from reportbuilder.stats.series import Cell, SeriesResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

CATEGORIES = ("Strongly agree", "Agree", "Neutral")
SEGMENT = "Total"
PCT_VALUES = (45.0, 30.0, 25.0)


def _make_series() -> SeriesResult:
    cells = {
        (cat, SEGMENT): Cell(pct=pct, count=float(pct), mean=None)
        for cat, pct in zip(CATEGORIES, PCT_VALUES)
    }
    return SeriesResult(
        categories=CATEGORIES,
        segments=(SEGMENT,),
        cells=cells,
        base_n={SEGMENT: 100},
        statistic="pct",
    )


def _make_slide():
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    return prs, slide


def _make_slot() -> Slot:
    return Slot(
        slide_index=0,
        left=Inches(1),
        top=Inches(1),
        width=Inches(8),
        height=Inches(5),
        name="slot1",
    )


# ---------------------------------------------------------------------------
# Test 1: registry key
# ---------------------------------------------------------------------------

def test_registry_key():
    """NATIVE_BUILDERS['vertical_bar'] must be build_column_chart."""
    from reportbuilder.render.native import NATIVE_BUILDERS
    from reportbuilder.render.native.column import build_column_chart

    assert NATIVE_BUILDERS["vertical_bar"] is build_column_chart


# ---------------------------------------------------------------------------
# Test 2: returns a graphic frame with chart + correct series values
# ---------------------------------------------------------------------------

def test_build_column_chart_returns_graphic_frame_with_correct_values():
    """build_column_chart returns a graphic frame whose chart has the fixture pct values."""
    from reportbuilder.render.native.column import build_column_chart

    prs, slide = _make_slide()
    slot = _make_slot()
    series = _make_series()

    gf = build_column_chart(slide, slot, series)

    assert gf.has_chart, "shape must be a chart graphic frame"
    chart = gf.chart
    assert len(chart.plots) > 0
    plot = chart.plots[0]
    assert len(plot.series) == 1
    values = tuple(plot.series[0].values)
    assert values == PCT_VALUES, f"expected {PCT_VALUES}, got {values}"


# ---------------------------------------------------------------------------
# Test 3: zero PICTURE shapes (editability gate)
# ---------------------------------------------------------------------------

def test_no_picture_shapes_on_slide():
    """Slide must contain ZERO MSO_SHAPE_TYPE.PICTURE shapes (chart must be native)."""
    from reportbuilder.render.native.column import build_column_chart

    prs, slide = _make_slide()
    slot = _make_slot()
    series = _make_series()

    build_column_chart(slide, slot, series)

    picture_shapes = [
        s for s in slide.shapes
        if s.shape_type == MSO_SHAPE_TYPE.PICTURE
    ]
    assert picture_shapes == [], (
        f"Found {len(picture_shapes)} PICTURE shapes — chart must be a native c:chart object"
    )


# ---------------------------------------------------------------------------
# Test 4: c:manualLayout element present in chartSpace
# ---------------------------------------------------------------------------

def test_manual_layout_element_present():
    """c:manualLayout must be present inside gf.chart._chartSpace after injection."""
    from reportbuilder.render.native.column import build_column_chart

    prs, slide = _make_slide()
    slot = _make_slot()
    series = _make_series()

    gf = build_column_chart(slide, slot, series)
    cs = gf.chart._chartSpace
    manual_layout = cs.find(".//" + qn("c:manualLayout"))
    assert manual_layout is not None, "c:manualLayout must be injected into chartSpace"


# ---------------------------------------------------------------------------
# Test 5: c:dLblPos present with val="outEnd"
# ---------------------------------------------------------------------------

def test_dlbl_pos_out_end():
    """c:dLblPos must be present in chartSpace with val='outEnd'."""
    from reportbuilder.render.native.column import build_column_chart

    prs, slide = _make_slide()
    slot = _make_slot()
    series = _make_series()

    gf = build_column_chart(slide, slot, series)
    cs = gf.chart._chartSpace
    dlbl_pos = cs.find(".//" + qn("c:dLblPos"))
    assert dlbl_pos is not None, "c:dLblPos element must be injected"
    assert dlbl_pos.get("val") == "outEnd", (
        f"c:dLblPos val must be 'outEnd', got {dlbl_pos.get('val')!r}"
    )


# ---------------------------------------------------------------------------
# Test 6: save + reopen without error (REQ-C-29a, the real feasibility gate)
# ---------------------------------------------------------------------------

def test_save_and_reopen_without_error():
    """Deck must save and reopen cleanly — guards REQ-C-29a (valid OOXML)."""
    from reportbuilder.render.native.column import build_column_chart

    prs, slide = _make_slide()
    slot = _make_slot()
    series = _make_series()

    build_column_chart(slide, slot, series)

    buf = io.BytesIO()
    prs.save(buf)
    buf.seek(0)

    # Must not raise
    prs2 = Presentation(buf)
    assert len(prs2.slides) == 1, "reopened presentation must have 1 slide"
