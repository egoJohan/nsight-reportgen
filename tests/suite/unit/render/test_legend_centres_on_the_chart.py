"""A legend below the chart is centred on the CHART, not on the axes.

`_draw_row_summary` reserves a strip on the right of the axes for the Top 2
column — `set_xlim(0, 118% of axis_max)`. The legend anchors at axes x=0.5,
which is then 59 % of the way across the DATA, so a five-entry legend sat
visibly right of the bars it describes. Measured on the reported slide: the bars
span 326–838 px and the legend 298–950, centred on 624 against the bars' 582.

What a legend belongs to is the data, so it centres on the data — the reserved
strip is furniture, and furniture does not move the thing it stands beside.
(Johan, 2026-09-17)
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

# A stacked chart is TRANSPOSED: the engine emits the scale levels as
# `categories` and the bars — here the statements — as `segments`. The builder
# summarises per BAR, so `row_summary_keys` names the segments.
LEVELS = ("Täysin eri mieltä", "Jokseenkin eri mieltä", "Ei samaa eikä eri mieltä",
          "Jokseenkin samaa mieltä", "Täysin samaa mieltä")
BARS = ("Työni on merkityksellistä", "Saan tukea esihenkilöltäni",
        "Voin kehittyä työssäni")


def _series(with_summary: bool) -> SeriesResult:
    cells = {(c, s): Cell(pct=v) for s in BARS
             for c, v in zip(LEVELS, (3.0, 9.0, 18.0, 25.0, 45.0))}
    extra = {}
    if with_summary:
        extra = {"row_summaries": (70.0, 64.0, 60.0), "row_summary_keys": BARS}
    return SeriesResult(categories=LEVELS, segments=BARS, cells=cells,
                        base_n={"Total": 1018}, statistic="pct", **extra)


def _geometry(with_summary: bool) -> dict:
    spec = ChartSpec(
        question_ref="q", chart_type="stacked_horizontal_bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(),
        row_summary_fn="top2_sum" if with_summary else "none",
        row_summary_label="Top 2" if with_summary else "")
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=_series(with_summary),
        fmt=spec.number_format)

    seen: dict = {}
    original = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        r = self.canvas.get_renderer()
        ax = self.axes[0]
        # Where the DATA lives, in pixels — x=0 to the chart's own maximum.
        lo = ax.transData.transform((0, 0))[0]
        hi = ax.transData.transform((100.0, 0))[0]
        seen["data_centre"] = (lo + hi) / 2
        leg = ax.get_legend()
        box = leg.get_window_extent(r)
        seen["legend_centre"] = box.x0 + box.width / 2
        seen["data_width"] = hi - lo
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["stacked_horizontal_bar"](ctx)
    finally:
        Figure.savefig = original
    return seen


def test_a_summary_column_does_not_push_the_legend_off_centre():
    """The defect. The Top 2 strip is 18 % of the axes, so the legend used to
    sit 9 % of the chart's width to the right of it."""
    g = _geometry(True)
    off_by = abs(g["legend_centre"] - g["data_centre"]) / g["data_width"]
    assert off_by < 0.01, (
        f"legend centre {g['legend_centre']:.0f} against the chart's "
        f"{g['data_centre']:.0f} — {off_by:.1%} of the chart's width")


def test_a_chart_without_a_summary_column_is_unchanged():
    """It was already centred here, and must stay so: this is every other
    stacked chart in every deck."""
    g = _geometry(False)
    off_by = abs(g["legend_centre"] - g["data_centre"]) / g["data_width"]
    assert off_by < 0.01, f"off by {off_by:.1%}"
