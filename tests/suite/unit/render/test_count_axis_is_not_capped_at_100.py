"""A count axis reads to the data, not to 100.

"Jos line chartissa tunnusluvuksi valitsee count, niin kuvaaja piirtyy väärin.
Käytetty pystyakselin asteikko ei asetu oikein lukumääriä raportoitaessa …
Lisäksi sama asteikon skaalausongelma esiintyy Sum-tunnusluvun kanssa."

`_value_axis(max_val, statistic)` has been right all along: percentages get the
fixed 0..100 scale, and counts, sums and means get nice round ticks covering
the real range — "otherwise a count of e.g. 600 would overflow a 0..100 axis".

The line builder never called it. It carried its own copy of the percentage
rule, `min(100.0, max(max_val * 1.20, 10.0))`, which caps EVERY statistic, so a
line of counts ran off the top of the chart and its points were drawn outside
the axes. The radar carried the same copy, `min(100.0, max_val * 1.15)`, and
had the same defect — unreported only because nobody had tried a count on one.

One rule in one place; `_value_axis` now lives in `_mpl` where all four
builders can reach it. (Johan, 2026-09-16)
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

_CATS = ("Harvemmin", "1-2 päivää", "3-4 päivää", "Pääsääntöisesti")
#: Counts well past 100 — the reported shape.
_COUNTS = (516, 448, 532, 604)


def _series(statistic: str, values) -> SeriesResult:
    # pct/count/mean are fields on Cell; anything else (sum, median) lives in
    # `extra`, which is how the engine stores a registered non-core statistic.
    def _cell(v: float) -> Cell:
        if statistic in ("pct", "count", "mean"):
            return Cell(**{statistic: float(v)})
        return Cell(extra=((statistic, float(v)),))

    cells = {(c, "Total"): _cell(v) for c, v in zip(_CATS, values)}
    return SeriesResult(categories=_CATS, segments=("Total",), cells=cells,
                        base_n={"Total": 2100}, statistic=statistic)


def _ylim(chart_type: str, statistic: str, values) -> tuple[float, float]:
    spec = ChartSpec(
        question_ref="q1", chart_type=chart_type, statistic=statistic,
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(title=True, subtitle=True, legend=True, n=True,
                                axis_names=True, filter_var=True,
                                data_labels=True))
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=_series(statistic, values),
        fmt=spec.number_format)

    seen: list[tuple[float, float]] = []
    original = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        for axes in self.axes:
            seen.append(axes.get_ylim())
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS[chart_type](ctx)
    finally:
        Figure.savefig = original
    return seen[0]


@pytest.mark.parametrize("statistic", ["count", "sum", "mean"])
def test_a_line_axis_reaches_the_biggest_count(statistic):
    """The defect: the axis stopped at 100 and the line left the chart."""
    _lo, hi = _ylim("line", statistic, _COUNTS)
    assert hi >= max(_COUNTS), (
        f"{statistic}: axis tops out at {hi} with data up to {max(_COUNTS)}")


@pytest.mark.parametrize("statistic", ["count", "sum"])
def test_a_radar_axis_reaches_the_biggest_count(statistic):
    """Same copied rule, same defect, simply never reported."""
    _lo, hi = _ylim("radar", statistic, _COUNTS)
    assert hi >= max(_COUNTS), f"{statistic}: radar tops out at {hi}"


def test_a_percentage_line_never_passes_100():
    """The cap is a CEILING, not a fixed axis: a percentage chart scales to its
    own data — 32 % of respondents against a 0..100 axis would be a chart of
    mostly empty space — and simply never reads past 100, because nothing can."""
    _lo, hi = _ylim("line", "pct", (32.0, 26.0, 20.0, 22.0))
    assert 32.0 <= hi <= 100.0


def test_a_small_percentage_line_is_unchanged():
    """The existing floor: a chart of tiny shares still reads to at least 10."""
    _lo, hi = _ylim("line", "pct", (3.0, 2.0, 1.0, 4.0))
    assert hi >= 10.0


def test_a_bar_chart_of_counts_was_already_right():
    """The comparison the report makes — "toimii oikein muissa kuvaajatyypeissä"
    — and the behaviour the line now matches."""
    _lo, hi = _ylim("vertical_bar", "count", _COUNTS)
    assert hi >= max(_COUNTS)
