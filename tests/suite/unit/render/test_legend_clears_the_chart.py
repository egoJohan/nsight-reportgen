"""The legend sits clear of the chart, and of the axis title under it.

"Maybe add a bit space between the legend and the chart data."

`_legend_below` anchored the legend 0.08 of the axes height below the plot,
whatever was already in that space. With an x-axis title drawn there the two
crowded each other, and even without one the row sat tight against the ticks.

The gap is now a little wider, and wider again when an axis title has to fit
between. Measured against the drawn artists rather than eyeballed, so a change
to either the title or the tick labels cannot quietly close it again.
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

LEVELS = ("Amazon", "Salesforce", "Aramco", "nSight", "Estrella", "En osaa sanoa")


def _series() -> SeriesResult:
    cells = {(l, "Total"): Cell(pct=100.0 / len(LEVELS)) for l in LEVELS}
    return SeriesResult(categories=LEVELS, segments=("Total",), cells=cells,
                        base_n={"Total": 1018}, statistic="pct")


def _gaps(axis_title: str = "") -> dict:
    """Vertical gap, in pixels, between the plot's bottom and the legend's top —
    and between the axis title and the legend when there is one."""
    spec = ChartSpec(
        question_ref="q", chart_type="stacked_vertical_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(), axis_x_title=axis_title)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=_series(), fmt=spec.number_format)
    out: dict = {}
    original = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        r = self.canvas.get_renderer()
        for axes in self.axes:
            leg = axes.get_legend()
            if leg is None:
                continue
            leg_box = leg.get_window_extent(r)
            out["plot_to_legend"] = axes.get_window_extent(r).y0 - leg_box.y1
            label = axes.xaxis.get_label()
            if label.get_text().strip():
                out["title_to_legend"] = label.get_window_extent(r).y0 - leg_box.y1
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["stacked_vertical_bar"](ctx)
    finally:
        Figure.savefig = original
    return out


def test_the_legend_does_not_touch_the_plot():
    assert _gaps()["plot_to_legend"] > 0


def test_the_legend_clears_the_axis_title():
    """The reported crowding: the title sits between them and needs its room."""
    assert _gaps("Yritys")["title_to_legend"] > 0


def test_an_axis_title_buys_more_room_than_none():
    """Not a fixed gap: the space grows to hold what is put in it."""
    assert _gaps("Yritys")["plot_to_legend"] > _gaps()["plot_to_legend"]
