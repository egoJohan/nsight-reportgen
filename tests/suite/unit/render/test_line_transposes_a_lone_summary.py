"""A summary statistic on a line chart draws a line, not a pile of dots.

A summary statistic — sum, mean, median — produces ONE category (the question)
times the classifier's groups. Drawn literally that is five points stacked on a
single x position: overlapping value labels, no line between anything, and a
legend explaining five colours that sit on top of each other.

`_as_one_series_per_group` already solves this, and the bar builder already
calls it: "Transposing hands it to the ordinary path as what it actually is:
one series over N categories." The line builder never did.

Reported as "Slide 15 is now somehow wrong" — and it was, whatever the axis
underneath it was doing. (Johan, 2026-09-16)
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

QUESTION = "Kuinka ylpeä olet omasta työstäsi?"
GROUPS = ("Alle 30", "30-44", "45-59", "60 tai yli")
SUMS = (896, 1283, 1758, 1439)


def _series(cats, statistic, values_by_seg):
    cells = {}
    for c in cats:
        for g, vals in values_by_seg.items():
            v = float(vals[cats.index(c)])
            cells[(c, g)] = (Cell(**{statistic: v})
                             if statistic in ("pct", "count", "mean")
                             else Cell(extra=((statistic, v),)))
    return SeriesResult(categories=tuple(cats), segments=tuple(values_by_seg),
                        cells=cells,
                        base_n={"Total": 1018, **{g: 250 for g in values_by_seg}},
                        statistic=statistic)


def _drawn(series) -> dict:
    spec = ChartSpec(
        question_ref="q", chart_type="line", statistic=series.statistic,
        classifying_var="ikaryhma", number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles())
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=series, fmt=spec.number_format)
    out: dict = {}
    original = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        lines, ticks = [], []
        for axes in self.axes:
            # Data lines only: `axhline` gridlines are Line2D as well, and they
            # have no marker.
            lines += [ln for ln in axes.lines
                      if len(ln.get_xdata()) > 0
                      and ln.get_marker() not in ("", "None", None)]
            ticks += [t.get_text().replace("\n", " ")
                      for t in axes.get_xticklabels() if t.get_text().strip()]
        out["points"] = max((len(ln.get_xdata()) for ln in lines), default=0)
        out["series"] = len(lines)
        out["ticks"] = ticks
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["line"](ctx)
    finally:
        Figure.savefig = original
    return out


@pytest.mark.parametrize("statistic", ["sum", "mean", "median"])
def test_the_groups_become_the_x_axis(statistic):
    """One point per group on one line, instead of four on one x."""
    drawn = _drawn(_series([QUESTION], statistic,
                           {g: [v] for g, v in zip(GROUPS, SUMS)}))
    assert drawn["points"] == len(GROUPS), drawn
    assert drawn["series"] == 1, drawn


def test_the_groups_are_named_on_the_axis():
    drawn = _drawn(_series([QUESTION], "sum",
                           {g: [v] for g, v in zip(GROUPS, SUMS)}))
    assert drawn["ticks"] == list(GROUPS), drawn


def test_a_distribution_is_untouched():
    """Several categories is a real line chart and must not be transposed."""
    cats = ["1- Ei lainkaan", "2", "3"]
    drawn = _drawn(_series(cats, "pct", {"Nainen": [10, 20, 30],
                                         "Mies": [12, 22, 32]}))
    assert drawn["series"] == 2 and drawn["points"] == 3, drawn


def test_one_group_is_untouched():
    """Nothing to transpose — a lone group stays a lone point."""
    drawn = _drawn(_series([QUESTION], "sum", {"Total": [5376]}))
    assert drawn["points"] == 1, drawn


def test_a_lone_category_that_is_an_ANSWER_is_untouched():
    """A distribution narrowed to one surviving answer is not a summary."""
    drawn = _drawn(_series(["Attendo"], "pct", {"Nainen": [60], "Mies": [55]}))
    assert drawn["series"] == 2, drawn
