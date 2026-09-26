"""A chart too dense to carry its numbers says so — to the author, not the slide.

25 departments on the default template's chart area gives each bar 4.55pt of
height. The value-label font floors at 5.5pt, so labelling them would overlap;
`_MIN_LABEL_BAR_PT` drops them instead, and it is right to. What was missing is
anyone SAYING so: the author got a chart with no numbers on it, no reason given,
and no hint that the same chart labels perfectly on a taller chart area.

It is a property of the RENDER, not of the chart: 25 categories label fine at
4.4in and do not at 3.0in. So it is recorded where the decision is made — one
rule, in the builder that applies it — and travels to the editor over the same
preview-header channel as the blank slide. (Johan, 2026-09-16)
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pytest
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit


def _series(n: int) -> SeriesResult:
    cats = tuple(str(i) for i in range(1, n + 1))
    return SeriesResult(
        categories=cats, segments=("Total",),
        cells={(c, "Total"): Cell(pct=100.0 / n) for c in cats},
        base_n={"Total": 1018}, statistic="pct")


def _notes(n_cats: int, height_in: float, chart_type: str = "horizontal_bar"):
    spec = ChartSpec(question_ref="q", chart_type=chart_type, statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    notes: list = []
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(height_in), name="s1"),
        style=StyleSpec(), spec=spec, series=_series(n_cats),
        fmt=spec.number_format, notes=notes)
    IMAGE_BUILDERS[chart_type](ctx)
    return notes


def test_a_short_slot_records_what_it_could_not_label():
    """The default template's chart area, too many categories even for numbers
    without their "%". (The reported 25 now fit once the sign is dropped — see
    the next test — so the warning is pinned on 30.)"""
    notes = _notes(30, 3.0)
    assert [n.kind for n in notes] == ["unlabelled"]
    assert notes[0].count == 30


def test_the_reported_25_are_numbered_without_their_sign():
    """25 categories at 3.0in: "43 %" is too tall for the bars, "43" is not —
    so they are numbered, without the sign, and nothing is raised. ("Remove the
    percentage from the number when we are short in space", 2026-09-26.)"""
    assert _notes(25, 3.0) == []


def test_the_same_chart_on_a_taller_slot_says_nothing():
    """Proof that this is about the RENDER, not the category count — the same 25
    categories carry their numbers when there is room, and an author warned
    about a chart that IS labelled would learn to ignore the warning."""
    assert _notes(25, 4.4) == []


def test_an_ordinary_chart_says_nothing():
    assert _notes(6, 4.4) == []


def test_nobody_collecting_is_not_an_error():
    """`notes` is optional: the deck export does not ask, and a builder that
    required a sink would crash every path that does not want one."""
    spec = ChartSpec(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(3.0), name="s1"),
        style=StyleSpec(), spec=spec, series=_series(25), fmt=spec.number_format)
    IMAGE_BUILDERS["horizontal_bar"](ctx)   # must not raise
