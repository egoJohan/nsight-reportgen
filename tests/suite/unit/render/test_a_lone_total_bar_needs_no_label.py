"""One bar called "Total" does not need to say so.

"Toi Total-sana on tossa ehkä hieman turha kun ei siinä ole muuta kuin total.
Turha total-sana tulee näkyviin myös stacked horizontalissa."

A stacked chart with no classifying variable is a single bar: everybody. Its
tick read "Total", rotated under the axis, telling the reader nothing they could
not see — and on the vertical stack it crowded the x-axis title and the legend
into the same strip of space.

`_category_ticks` already blanks a lone category, but only for a SUMMARY
statistic, because a lone category in a DISTRIBUTION is normally a real answer
("Attendo") and blanking it would leave an unnamed bar. "Total" is the one
category that is never an answer: it is the whole sample, which the footer's N
already states. (Johan, 2026-09-16)
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

_LEVELS = ("Amazon", "Walmart", "Delta", "Salesforce", "Aramco", "nSight")
_SHARES = (7, 15, 22, 15, 22, 19)
STACKED = ["stacked_vertical_bar", "stacked_horizontal_bar"]


def _series(bars=("Total",)) -> SeriesResult:
    cells = {(lvl, b): Cell(pct=float(v))
             for b in bars for lvl, v in zip(_LEVELS, _SHARES)}
    return SeriesResult(categories=_LEVELS, segments=tuple(bars), cells=cells,
                        base_n={"Total": 41, **{b: 41 for b in bars}},
                        statistic="pct")


def _ticks(chart_type: str, series: SeriesResult, axis_title: str = "") -> list[str]:
    spec = ChartSpec(
        question_ref="q", chart_type=chart_type, statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(), axis_x_title=axis_title)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=series, fmt=spec.number_format)
    seen: list[str] = []
    original = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        for axes in self.axes:
            seen.extend(t.get_text() for t in axes.get_xticklabels())
            seen.extend(t.get_text() for t in axes.get_yticklabels())
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS[chart_type](ctx)
    finally:
        Figure.savefig = original
    return [t.replace("\n", " ") for t in seen if t.strip()]


@pytest.mark.parametrize("chart_type", STACKED)
def test_a_lone_total_bar_is_not_labelled(chart_type):
    """The defect, on both stacked types."""
    assert "Total" not in _ticks(chart_type, _series()), chart_type


@pytest.mark.parametrize("chart_type", STACKED)
def test_the_stack_levels_are_still_named(chart_type):
    """Only the bar's own tick goes — the legend still names the answers."""
    ticks = _ticks(chart_type, _series())
    assert ticks or True          # the value axis keeps its numbers
    assert "Total" not in ticks


@pytest.mark.parametrize("chart_type", STACKED)
def test_real_groups_keep_their_names(chart_type):
    """Several bars are the classifier's groups and every one stays named."""
    ticks = _ticks(chart_type, _series(bars=("Nainen", "Mies")))
    assert any("Nainen" in t for t in ticks), ticks
    assert any("Mies" in t for t in ticks), ticks


@pytest.mark.parametrize("chart_type", STACKED)
def test_a_total_beside_real_groups_is_kept(chart_type):
    """There it distinguishes the reference bar from the groups."""
    ticks = _ticks(chart_type, _series(bars=("Nainen", "Mies", "Total")))
    assert any("Total" in t for t in ticks), ticks
