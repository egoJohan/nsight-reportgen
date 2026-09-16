"""A label the author typed is drawn as the author typed it.

"Category labels määritykset jäävät joissain tilanteissa päivittymättä kuvaan
(ainakin stacked horizontal barissa)."

`_legend_below` shortens a legend to bare scale points when EVERY label begins
with a digit — "1 - Ei kovin tärkeä", "2", … "7 - Erittäin tärkeä" becomes
1 2 3 4 5 6 7, which keeps the legend short and even and moves the endpoint
wording to the subtitle. Good default, and it was eating the author's work: the
engine applied their renaming and the renderer discarded it a moment later.
Retype "1 - Ei kovin tärkeä" as "1 - Ei tärkeä" and the picture does not move,
because both shorten to "1".

Found on the real slide (Suomalainen Työ, stacked horizontal bar split by
country): the engine computed
('1 - Ei kovin tärkeä', '2', … '7 - Erittäin tärkeä') and the legend drew
1 2 3 4 5 6 7.

So: the moment the author names ANY category themselves, the shortener stands
down for that chart. Not just for the renamed one — a legend reading
"Ei tärkeä, 2, 3" would be the same chart telling its levels two different ways.
(Johan, 2026-09-16)
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pytest
from matplotlib.figure import Figure
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit

#: The real scale from the reported slide.
_LEVELS = ("1 - Ei kovin tärkeä", "2", "3", "4", "5", "6", "7 - Erittäin tärkeä")
_GROUPS = ("Suomi", "Ruotsi", "Saksa")


def _series(levels=_LEVELS) -> SeriesResult:
    cells = {}
    for i, lvl in enumerate(levels):
        for j, g in enumerate(_GROUPS):
            cells[(lvl, g)] = Cell(pct=float(10 + i + j))
    return SeriesResult(
        categories=tuple(levels), segments=_GROUPS, cells=cells,
        base_n={"Total": 2968, **{g: 985 for g in _GROUPS}}, statistic="pct")


def _legend_texts(levels=_LEVELS, overrides=()) -> list[str]:
    spec = ChartSpec(
        question_ref="q1", chart_type="stacked_horizontal_bar", statistic="pct",
        classifying_var="country", number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(title=True, subtitle=True, legend=True, n=True,
                                axis_names=True, filter_var=True, data_labels=True),
        category_label_overrides=tuple(overrides))
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=_series(levels),
        fmt=spec.number_format)

    seen: list[str] = []
    original = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        for axes in self.axes:
            leg = axes.get_legend()
            if leg is not None:
                seen.extend(t.get_text() for t in leg.get_texts())
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["stacked_horizontal_bar"](ctx)
    finally:
        Figure.savefig = original
    return seen


def test_an_untouched_numeric_scale_is_still_shortened():
    """The default that earns its keep — seven long labels would not fit."""
    assert _legend_texts() == ["1", "2", "3", "4", "5", "6", "7"]


def test_a_renamed_level_is_shown_as_the_author_wrote_it():
    """The defect: the wording was discarded at draw time."""
    texts = _legend_texts(
        levels=("Ei tärkeä", "2", "3", "4", "5", "6", "7 - Erittäin tärkeä"),
        overrides=[["1 - Ei kovin tärkeä", "Ei tärkeä"]])
    assert "Ei tärkeä" in texts, texts


def test_a_rename_that_keeps_its_number_still_shows():
    """The sharpest form: both old and new shorten to "1", so nothing moved on
    the slide however many times the author retyped it."""
    texts = _legend_texts(
        levels=("1 - Ei tärkeä", "2", "3", "4", "5", "6", "7 - Erittäin tärkeä"),
        overrides=[["1 - Ei kovin tärkeä", "1 - Ei tärkeä"]])
    assert "1 - Ei tärkeä" in texts, texts


def test_the_whole_legend_stops_shortening_together():
    """One level named and the rest numbers would say the same thing two ways."""
    texts = _legend_texts(
        levels=("1 - Ei tärkeä", "2", "3", "4", "5", "6", "7 - Erittäin tärkeä"),
        overrides=[["1 - Ei kovin tärkeä", "1 - Ei tärkeä"]])
    assert "7 - Erittäin tärkeä" in texts, texts


def test_an_override_for_another_chart_does_not_disable_it():
    """Overrides are stored per slide but name categories; one that matches
    nothing on THIS chart must not turn the shortener off."""
    texts = _legend_texts(overrides=[["Jokin aivan muu", "Muu"]])
    assert texts == ["1", "2", "3", "4", "5", "6", "7"]
