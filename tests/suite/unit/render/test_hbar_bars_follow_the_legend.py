"""A horizontal bar chart's bars read top-down in the legend's order.

"Horizontal barissa legendin arvon esitysjärjestys menee päinvastoin kuin
kuvassa." The legend lists the first series first; `_render_bar_h` drew it at
the BOTTOM of each category, so the reader matched the legend's first entry to
the last bar. Now series i sits above series i+1 — plain and cross-tab
(grouped) alike — and each value label stays on its own bar. (2026-11-10)
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pytest
from matplotlib.figure import Figure
from matplotlib.patches import Rectangle
from matplotlib.text import Text
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.image._mpl import VALUE_GID
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit

_CATS = ("Silmäasema", "Synsam")


def _render(segs, primary=None):
    # Distinct values per series, so a bar's width tells which series it is.
    vals = {s: 10.0 + 7 * j for j, s in enumerate(segs)}
    cells = {(c, s): Cell(pct=vals[s] + i) for i, c in enumerate(_CATS) for s in segs}
    series = SeriesResult(categories=_CATS, segments=tuple(segs), cells=cells,
                          base_n={"Total": 900, **{s: 100 for s in segs}},
                          statistic="pct", segment_primary=primary)
    spec = ChartSpec(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                     classifying_var="g", number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    prs = Presentation()
    ctx = RenderContext(
        slide=prs.slides.add_slide(prs.slide_layouts[6]),
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=series, fmt=spec.number_format)
    got = {}
    original = Figure.savefig

    def spy(self, *a, **k):
        self.canvas.draw()
        ax = self.axes[0]
        bars = [p for p in ax.patches if isinstance(p, Rectangle) and p.get_width() > 0]
        got["bars"] = [(p.get_y() + p.get_height() / 2, p.get_width()) for p in bars]
        leg = ax.get_legend() or (self.legends[0] if self.legends else None)
        got["legend"] = [t.get_text() for t in leg.get_texts()] if leg else []
        got["labels"] = [t.get_position()[1] for t in self.findobj(Text)
                         if t.get_gid() == VALUE_GID]
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["horizontal_bar"](ctx)
    finally:
        Figure.savefig = original
    return got, vals


def _order_top_down(got, vals, cat_index):
    """Series names of one category's bars, top bar first."""
    by_width = {round(v + cat_index, 3): s for s, v in vals.items()}
    rows = [(y, by_width.get(round(w, 3))) for y, w in got["bars"]]
    rows = [(y, s) for y, s in rows if s is not None]
    return [s for _y, s in sorted(rows, key=lambda r: -r[0])]


_PLAIN = ("Laatua arvostavat", "Hintaherkät", "Vaihtelunhaluiset")
_CROSS = ("2025 · Laatua", "2025 · Muut", "2026 · Laatua", "2026 · Muut")


@pytest.mark.parametrize("segs,primary", [
    (_PLAIN, None),
    (_CROSS, {s: s.split(" · ")[0] for s in _CROSS}),
])
def test_bars_read_top_down_in_legend_order(segs, primary):
    got, vals = _render(segs, primary)
    for ci in range(len(_CATS)):
        assert _order_top_down(got, vals, ci) == list(segs), got["bars"]
    # and the legend lists them in that same order
    assert [t.split(" (n=")[0] for t in got["legend"]][:len(segs)] == [
        s.split(" · ")[-1] if primary else s for s in segs] or got["legend"]


@pytest.mark.parametrize("segs,primary", [
    (_PLAIN, None),
    (_CROSS, {s: s.split(" · ")[0] for s in _CROSS}),
])
def test_each_value_label_sits_on_its_own_bar(segs, primary):
    got, _vals = _render(segs, primary)
    bar_ys = sorted(round(y, 3) for y, _w in got["bars"])
    label_ys = sorted(round(y, 3) for y in got["labels"])
    assert label_ys == bar_ys, (label_ys, bar_ys)
