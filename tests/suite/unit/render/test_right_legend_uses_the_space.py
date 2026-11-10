"""A bar chart's right-hand legend takes the width its labels need, and the plot the rest.

"Why doesn't legend box use all space available to the right?" With more than
`_LEGEND_BELOW_MAX` series the legend goes to the right, and `_place_series_legend`
wrapped every label at a fixed 26 characters and shrank the plot to a fixed
72 %: "2026 · Hintaherkät (n=235)" broke onto two lines while the space beside
the legend stayed empty. Now short labels stay on one line, the legend ends at
the figure's right edge, and only a label wider than the room left wraps —
full text, never cut. (2026-11-10)
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import pytest
from matplotlib.figure import Figure
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit

_CATS = ("Silmäasema", "Specsavers", "Synsam")
_SHORT = ("2026 · Laatua arvostavat", "2026 · Hintaherkät", "2026 · Vaihtelunhaluiset",
          "2026 · Hintatietoiset", "2026 · Palvelua kaipaavat", "2026 · Tyylitietoiset")
_LONG = ("Laatua arvostavat asiakkaat, jotka ostavat kalliimpia kehyksiä ja linssejä",
         *_SHORT[1:])


def _render(chart_type, segs):
    cells = {(c, s): Cell(pct=40.0 + 5 * j + i)
             for i, c in enumerate(_CATS) for j, s in enumerate(segs)}
    series = SeriesResult(categories=_CATS, segments=tuple(segs), cells=cells,
                          base_n={"Total": 900, **{s: 100 for s in segs}},
                          statistic="pct")
    spec = ChartSpec(question_ref="q", chart_type=chart_type, statistic="pct",
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
        r = self.canvas.get_renderer()
        ax = self.axes[0]
        leg = ax.get_legend()
        got["texts"] = [t.get_text() for t in leg.get_texts()]
        got["legend"] = leg.get_window_extent(r)
        got["axes"] = ax.get_window_extent(r)
        got["fig"] = self.bbox
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS[chart_type](ctx)
    finally:
        Figure.savefig = original
    return got


_TYPES = ["horizontal_bar", "vertical_bar"]


@pytest.mark.parametrize("chart_type", _TYPES)
def test_short_labels_stay_on_one_line(chart_type):
    got = _render(chart_type, _SHORT)
    assert not any("\n" in t for t in got["texts"]), got["texts"]


@pytest.mark.parametrize("chart_type", _TYPES)
def test_the_legend_reaches_the_right_edge_and_stays_inside(chart_type):
    got = _render(chart_type, _SHORT)
    fig, leg = got["fig"], got["legend"]
    assert leg.x1 <= fig.x1 + 1
    assert fig.x1 - leg.x1 < 0.03 * fig.width, (leg.x1, fig.x1)
    # ...and the plot runs up to the legend, not to a fixed 72 %
    assert leg.x0 - got["axes"].x1 < 0.04 * fig.width


@pytest.mark.parametrize("chart_type", _TYPES)
def test_a_label_too_long_for_the_room_wraps_in_full(chart_type):
    got = _render(chart_type, _LONG)
    first = got["texts"][0]
    assert "\n" in first and "…" not in first
    assert first.replace("\n", " ").startswith(_LONG[0])
    assert got["legend"].x1 <= got["fig"].x1 + 1
