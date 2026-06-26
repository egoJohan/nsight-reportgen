"""Tests for R4 polish: long-label wrapping/truncation + 'Not answered' grey bar.

R4.1 — Long-label handling:
  - _wrap_label wraps labels > 22 chars to ≤ 2 lines with '…' on overflow
  - _truncate_label clips labels > 42 chars with '…'
  - Horizontal-bar renderer applies wrapped display labels without error
  - Short labels (≤ 22 chars) pass through unchanged

R4.2 — "Not answered" bar coloring:
  - The "Not answered" bar is rendered in MUTED grey, not TEAL
  - All other bars keep their teal series colour
"""
from __future__ import annotations

import io

import pytest
import matplotlib
matplotlib.use("Agg")
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches
from PIL import Image

from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL
from reportbuilder.render.house_style import MUTED, TEAL


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ctx(chart_type: str, series: SeriesResult) -> tuple:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slot = Slot(slide_index=0, left=Inches(1), top=Inches(1),
                width=Inches(8), height=Inches(5), name="slot1")
    spec = ChartSpec(
        question_ref="q1", chart_type=chart_type, statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="slot1",
        elements=ElementToggles(title=True, data_labels=True, legend=True),
    )
    ctx = RenderContext(slide=slide, slot=slot, style=StyleSpec(),
                       spec=spec, series=series, fmt=spec.number_format)
    return prs, slide, slot, ctx


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _count_color_pixels(blob: bytes, hex_color: str, tolerance: int = 8) -> int:
    """Count pixels in blob matching hex_color within tolerance."""
    img = Image.open(io.BytesIO(blob)).convert("RGB")
    r, g, b = _hex_to_rgb(hex_color)
    return sum(
        1 for px in img.getdata()
        if abs(px[0] - r) <= tolerance and abs(px[1] - g) <= tolerance and abs(px[2] - b) <= tolerance
    )


def _get_png_blob(slide) -> bytes:
    pics = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pics) == 1, f"Expected 1 picture; found {len(pics)}"
    return pics[0].image.blob


# ---------------------------------------------------------------------------
# R4.1 — Label helper unit tests
# ---------------------------------------------------------------------------

class TestWrapLabel:
    """Unit tests for _wrap_label helper (R4.1)."""

    def test_short_label_unchanged(self):
        """Labels ≤ 22 chars pass through _wrap_label unchanged."""
        from reportbuilder.render.image.bars import _wrap_label
        assert _wrap_label("Yes") == "Yes"
        assert _wrap_label("Kyllä, joskus") == "Kyllä, joskus"
        assert _wrap_label("A" * 22) == "A" * 22

    def test_long_label_wrapped_to_two_lines(self):
        """Labels > 22 chars are wrapped; result contains a newline."""
        from reportbuilder.render.image.bars import _wrap_label
        long = "Hoitajat kuuntelevat toiveitani"   # 31 chars
        result = _wrap_label(long)
        assert "\n" in result, f"Expected newline in wrapped label; got {result!r}"
        for line in result.split("\n"):
            assert len(line) <= 22, f"Line too long: {line!r}"

    def test_very_long_label_ellipsized(self):
        """Labels that cannot fit in 2 lines end with '…'."""
        from reportbuilder.render.image.bars import _wrap_label
        very_long = "Hoitajat kuuntelevat toiveitani ja tarpeitani erittäin hyvin kaikissa tilanteissa"
        result = _wrap_label(very_long)
        assert result.endswith("…"), f"Expected trailing ellipsis; got {result!r}"
        lines = result.split("\n")
        assert len(lines) <= 2, f"Should be at most 2 lines; got {lines!r}"


class TestTruncateLabel:
    """Unit tests for _truncate_label helper (R4.1)."""

    def test_short_label_unchanged(self):
        """Labels ≤ 42 chars pass through _truncate_label unchanged."""
        from reportbuilder.render.image.bars import _truncate_label
        assert _truncate_label("Short") == "Short"
        assert _truncate_label("A" * 42) == "A" * 42

    def test_long_label_truncated_with_ellipsis(self):
        """Labels > 42 chars are truncated to 42 chars ending with '…'."""
        from reportbuilder.render.image.bars import _truncate_label
        long = "A" * 60
        result = _truncate_label(long)
        assert result.endswith("…"), f"Expected trailing ellipsis; got {result!r}"
        assert len(result) == 42, f"Expected length 42; got {len(result)}"

    def test_custom_max_chars(self):
        """_truncate_label respects an explicit max_chars argument."""
        from reportbuilder.render.image.bars import _truncate_label
        result = _truncate_label("ABCDEFGHIJ", max_chars=5)
        assert result == "ABCD…", f"Got {result!r}"


# ---------------------------------------------------------------------------
# R4.1 — Render with long labels (smoke test)
# ---------------------------------------------------------------------------

def _long_cat_series() -> SeriesResult:
    """Series with var11-style long category labels (multi-sentence options)."""
    cats = (
        "Hoitajat kuuntelevat toiveitani ja tarpeitani",
        "Hoitajat ovat ystävällisiä ja kohtelevat minua kunnioittavasti",
        "Saan tarvitsemaani apua päivittäisissä toimissa",
        "Minua kohdellaan tasa-arvoisesti ja oikeudenmukaisesti",
        "Ruoka on maukasta ja monipuolista",
        "En osaa sanoa",
    )
    cells = {(c, "Total"): Cell(pct=float(60 - i * 8)) for i, c in enumerate(cats)}
    return SeriesResult(categories=cats, segments=("Total",), cells=cells,
                        base_n={"Total": 200}, statistic="pct")


def test_long_labels_render_without_error():
    """build_image_bar renders a long-label question without error (R4.1)."""
    from reportbuilder.render.image.bars import build_image_bar
    series = _long_cat_series()
    prs, slide, slot, ctx = _make_ctx("horizontal_bar", series)
    build_image_bar(ctx)
    blob = _get_png_blob(slide)
    img = Image.open(io.BytesIO(blob))
    w, h = img.size
    assert w > 0 and h > 0, "PNG must have positive dimensions"


def test_long_labels_produces_valid_png():
    """build_image_bar with long labels produces a non-trivial PNG (R4.1)."""
    from reportbuilder.render.image.bars import build_image_bar
    series = _long_cat_series()
    prs, slide, slot, ctx = _make_ctx("horizontal_bar", series)
    build_image_bar(ctx)
    blob = _get_png_blob(slide)
    assert len(blob) > 5000, "PNG blob should be non-trivially sized"


# ---------------------------------------------------------------------------
# R4.2 — "Not answered" bar is MUTED grey
# ---------------------------------------------------------------------------

def _na_series() -> SeriesResult:
    """Opinion series including a 'Not answered' category."""
    cats = ("Erittäin huono", "Huono", "Hyvä", "Erittäin hyvä", NOT_ANSWERED_LABEL)
    cells = {(c, "Total"): Cell(pct=v) for c, v in zip(cats, [5.0, 26.0, 47.0, 10.0, 12.0])}
    return SeriesResult(categories=cats, segments=("Total",), cells=cells,
                        base_n={"Total": 300}, statistic="pct")


def test_not_answered_bar_has_muted_pixels():
    """build_image_bar colors the 'Not answered' bar MUTED grey (R4.2).

    We check that the PNG contains MUTED-coloured pixels; TEAL pixels are
    also present (from the other bars).
    """
    from reportbuilder.render.image.bars import build_image_bar
    series = _na_series()
    prs, slide, slot, ctx = _make_ctx("horizontal_bar", series)
    build_image_bar(ctx)
    blob = _get_png_blob(slide)

    muted_count = _count_color_pixels(blob, MUTED, tolerance=10)
    teal_count = _count_color_pixels(blob, TEAL, tolerance=10)
    assert muted_count > 50, (
        f"Expected MUTED grey pixels in 'Not answered' bar; found {muted_count}"
    )
    assert teal_count > 50, (
        f"Expected TEAL pixels in real-response bars; found {teal_count}"
    )


def test_series_without_na_has_no_muted_bars():
    """build_image_bar without 'Not answered' category has no MUTED bar pixels (R4.2)."""
    from reportbuilder.render.image.bars import build_image_bar
    cats = ("Erittäin huono", "Huono", "Hyvä", "Erittäin hyvä")
    cells = {(c, "Total"): Cell(pct=v) for c, v in zip(cats, [5.0, 26.0, 47.0, 22.0])}
    series = SeriesResult(categories=cats, segments=("Total",), cells=cells,
                          base_n={"Total": 300}, statistic="pct")
    prs, slide, slot, ctx = _make_ctx("horizontal_bar", series)
    build_image_bar(ctx)
    blob = _get_png_blob(slide)

    muted_count = _count_color_pixels(blob, MUTED, tolerance=5)
    # MUTED is also used for axis tick labels; we allow some MUTED pixels from
    # the tick text but expect far fewer than with a dedicated MUTED bar.
    assert muted_count < 5000, (
        f"No MUTED bars expected when 'Not answered' is absent; found {muted_count} pixels"
    )
