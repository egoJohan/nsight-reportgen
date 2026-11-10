"""The line round a legend can be switched off.

"Voisiko legendin ympärillä olevan reunaviivan jättää pois tick boxilla (do not
show legend frame)." The pie's, the row of pies', the combo's and the line's
legends were drawn in a thin frame and there was no way to decline it.

`elements.legend_frame` turns it off, for every builder at once: they all frame
their legend through `_mpl.frame_legend`. Default True, so nothing already
saved changes — the first test pins exactly that. (2026-11-10)
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

_CATS = ("Päivittäin", "Viikoittain", "Harvemmin")
_GROUPS = ("Suomi", "Ruotsi", "Saksa")


def _series(groups) -> SeriesResult:
    cells = {(c, g): Cell(pct=float(20 + i * 5 + j))
             for i, c in enumerate(_CATS) for j, g in enumerate(groups)}
    return SeriesResult(categories=_CATS, segments=groups, cells=cells,
                        base_n={"Total": 1496, **{g: 500 for g in groups}},
                        statistic="pct")


def _legend_frames(chart_type: str, classified: bool, **toggles) -> list[bool]:
    """frame_on of every legend the builder drew, figure- and axes-level."""
    groups = _GROUPS if classified else ("Total",)
    spec = ChartSpec(
        question_ref="q1", chart_type=chart_type, statistic="pct",
        classifying_var="country" if classified else None,
        number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
        template_slot="s1", elements=ElementToggles(**toggles))
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=_series(groups), fmt=spec.number_format)
    seen: list[bool] = []
    original = Figure.savefig

    def spy(self, *a, **k):
        legs = list(self.legends) + [ax.get_legend() for ax in self.axes]
        seen.extend(leg.get_frame_on() for leg in legs if leg is not None)
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS[chart_type](ctx)
    finally:
        Figure.savefig = original
    return seen


# (chart type, classified): the single pie's category legend and the row of
# pies' shared legend are two separate code paths.
_FRAMED = [("pie", False), ("pie", True), ("doughnut", False), ("doughnut", True),
           ("line", True), ("combo", True)]


@pytest.mark.parametrize("chart_type,classified", _FRAMED)
def test_a_legend_is_framed_by_default(chart_type, classified):
    frames = _legend_frames(chart_type, classified)
    assert frames and all(frames), frames


@pytest.mark.parametrize("chart_type,classified", _FRAMED)
def test_the_frame_can_be_switched_off(chart_type, classified):
    frames = _legend_frames(chart_type, classified, legend_frame=False)
    assert frames and not any(frames), frames


def test_old_reports_without_the_key_keep_their_frame():
    from reportbuilder.model.report import ElementToggles as ET
    assert ET().legend_frame is True
