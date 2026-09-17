"""A combo finds its secondary half by what the series SAYS, not by guessing.

The split read `statistic_of(seg) == "mean"`. A combo's secondary variable is a
mean, so that looked right — until the series' own statistic is `mean` too, when
`statistic_of` falls back to it for every segment and the whole chart is
"secondary": no bars at all, every group a line on the right-hand axis, and the
left axis left at matplotlib's untouched 0.0–1.0 printed beside data it does not
describe.

That is not an exotic case. `_battery` returns `statistic="mean"` whatever the
spec asks for, so EVERY combo on a battery drew zero bars — the author never
chose "Mean" at all.

The fact was never in doubt: `_combo_two_var` builds
`segments = bar_segments + (secondary_label,)` and records which is which in
`segment_statistics`. The renderer threw that away and re-derived it from a
value. So ask the right question — "does this segment measure something OTHER
than the series does?" — which is what `segment_statistics` exists to answer, and
is false for every segment when there is no second measure. (Johan, 2026-09-17)
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
from reportbuilder.render.image.combo import split_primary_and_secondary_segments
from reportbuilder.stats.series import Cell, SeriesResult

pytestmark = pytest.mark.unit

CATS = ("1", "2", "3")


def _series(segments, statistic, segment_statistics=None) -> SeriesResult:
    field = "mean" if statistic == "mean" else "pct"
    cells = {(c, s): Cell(**{field: 3.0 + i * 0.4})
             for i, c in enumerate(CATS) for s in segments}
    return SeriesResult(
        categories=CATS, segments=tuple(segments), cells=cells,
        base_n={s: 100 for s in segments} | {"Total": 100},
        statistic=statistic, segment_statistics=segment_statistics)


def _render(series) -> dict:
    spec = ChartSpec(
        question_ref="q", chart_type="combo", statistic=series.statistic,
        classifying_var="sukup", number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles())
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=series, fmt=spec.number_format)

    seen: dict = {}
    from matplotlib.figure import Figure
    original = Figure.savefig

    def spy(self, *a, **k):
        from matplotlib.container import BarContainer
        ax = self.axes[0]
        seen["bars"] = sum(1 for c in ax.containers if isinstance(c, BarContainer))
        seen["left_ylim"] = ax.get_ylim()
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["combo"](ctx)
    finally:
        Figure.savefig = original
    return seen


# ---------------------------------------------------------------------------
# The split itself
# ---------------------------------------------------------------------------

def test_a_mean_series_without_a_second_measure_still_has_a_primary_half():
    """The defect: every segment read as "the line"."""
    segs = ("Miehet", "Naiset", "Total")
    primary, secondary = split_primary_and_secondary_segments(
        _series(segs, "mean"), segs)
    assert primary, f"nothing was left to draw as the primary half: {secondary}"


def test_a_real_second_measure_is_still_found():
    segs = ("Miehet", "Naiset", "indeksi")
    primary, secondary = split_primary_and_secondary_segments(
        _series(segs, "pct",
                {"Miehet": "pct", "Naiset": "pct", "indeksi": "mean"}), segs)
    assert primary == ["Miehet", "Naiset"] and secondary == ["indeksi"]


def test_the_second_measure_is_whatever_differs_not_whatever_is_a_mean():
    """A count secondary against percentage bars is the same shape and must
    split the same way — keying on the literal "mean" made this chart's
    secondary half indistinguishable from its primary."""
    segs = ("Miehet", "Naiset", "vastaajia")
    primary, secondary = split_primary_and_secondary_segments(
        _series(segs, "pct",
                {"Miehet": "pct", "Naiset": "pct", "vastaajia": "count"}), segs)
    assert primary == ["Miehet", "Naiset"] and secondary == ["vastaajia"]


# ---------------------------------------------------------------------------
# What actually reaches the slide
# ---------------------------------------------------------------------------

def test_a_battery_combo_draws_bars():
    """`_battery` reports statistic="mean" whatever the spec says, so this is
    every combo on every battery — reached without the author choosing Mean."""
    drawn = _render(_series(("Miehet", "Naiset", "Total"), "mean"))
    assert drawn["bars"] >= 1, "the chart drew no bars at all"


def test_the_left_axis_is_not_left_at_matplotlibs_default():
    """0.0–1.0 printed down the side of a chart whose values are 3.0–4.6 is an
    axis belonging to no data on the slide."""
    drawn = _render(_series(("Miehet", "Naiset", "Total"), "mean"))
    assert drawn["left_ylim"] != (0.0, 1.0)


# ---------------------------------------------------------------------------
# A bar's length is its value
# ---------------------------------------------------------------------------

def _secondary_bar_geometry(values) -> dict:
    """Render a combo whose secondary half is BARS; report what the axis does."""
    segs = ("Osuus", "indeksi")
    cells = {}
    for i, c in enumerate(CATS):
        cells[(c, "Osuus")] = Cell(pct=40.0 + i * 5)
        cells[(c, "indeksi")] = Cell(pct=values[i])
    series = SeriesResult(
        categories=CATS, segments=segs, cells=cells,
        base_n={"Osuus": 100, "indeksi": 100, "Total": 100}, statistic="pct",
        segment_statistics={"Osuus": "pct", "indeksi": "mean"})
    spec = ChartSpec(
        question_ref="q", chart_type="combo", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(),
        options={"combo_secondary": "indeksi", "combo_secondary_type": "bar"})
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=series, fmt=spec.number_format)

    seen: dict = {}
    from matplotlib.figure import Figure
    original = Figure.savefig

    def spy(self, *a, **k):
        ax2 = self.axes[-1]
        floor = ax2.get_ylim()[0]
        heights = [p.get_height() for c in ax2.containers for p in c.patches]
        seen["floor"] = floor
        seen["visible"] = [h - floor for h in heights]
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["combo"](ctx)
    finally:
        Figure.savefig = original
    return seen


def test_secondary_bars_are_measured_from_zero():
    """The defect: means 4.1 / 4.3 / 4.5 on an axis starting at 4.036 drew as
    0.064 / 0.264 / 0.464 — the tallest bar 7.25x the shortest, where the true
    ratio is 1.10x. A bar's LENGTH is its value; suppressing the baseline makes
    the picture say something the numbers do not.

    A line is exempt and stays zero-suppressed: it carries no length, only a
    position relative to its neighbours, which is what makes a flat index
    readable at all.
    """
    g = _secondary_bar_geometry([4.1, 4.3, 4.5])
    assert g["floor"] <= 0.0, f"the bar axis starts at {g['floor']}, not at zero"
    ratio = g["visible"][-1] / g["visible"][0]
    assert ratio == pytest.approx(4.5 / 4.1, rel=0.02), (
        f"drawn ratio {ratio:.2f}x for a true ratio of {4.5 / 4.1:.2f}x")


# ---------------------------------------------------------------------------
# One measure, one scale
# ---------------------------------------------------------------------------

def _axes_count(series) -> int:
    from matplotlib.figure import Figure
    spec = ChartSpec(
        question_ref="q", chart_type="combo", statistic=series.statistic,
        classifying_var="sukup", number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles())
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=series, fmt=spec.number_format)
    seen: dict = {}
    original = Figure.savefig

    def spy(self, *a, **k):
        seen["axes"] = len(self.axes)
        seen["ylims"] = [ax.get_ylim() for ax in self.axes]
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["combo"](ctx)
    finally:
        Figure.savefig = original
    return seen


def test_one_measure_is_drawn_on_one_axis():
    """A combo with no second measure is three views of the SAME quantity —
    percentages, or means on one scale. Putting some of them on a right-hand
    axis with its own range means a line at 3.5 can sit below a bar of 3.2, and
    a reader comparing them is reading two different rulers. The second axis is
    what a genuine second MEASURE needs; without one there is nothing for it to
    measure.
    """
    seen = _axes_count(_series(("Miehet", "Naiset", "Total"), "mean"))
    assert seen["axes"] == 1, f"drew {seen['axes']} scales for one measure"


def test_two_measures_still_get_two_axes():
    """The control: a real secondary variable is on its own scale and must keep
    its own axis, which is the whole point of the chart type."""
    seen = _axes_count(_series(
        ("Miehet", "Naiset", "indeksi"), "pct",
        {"Miehet": "pct", "Naiset": "pct", "indeksi": "mean"}))
    assert seen["axes"] == 2


def test_one_axis_does_not_name_every_group_twice():
    """Sharing an axis, `ax2` IS `ax`, and asking both for their legend entries
    hands back the same ones again."""
    from matplotlib.figure import Figure
    series = _series(("Miehet", "Naiset", "Total"), "mean")
    spec = ChartSpec(
        question_ref="q", chart_type="combo", statistic="mean",
        classifying_var="sukup", number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles())
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ctx = RenderContext(
        slide=slide,
        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                  width=Inches(12.3), height=Inches(4.4), name="s1"),
        style=StyleSpec(), spec=spec, series=series, fmt=spec.number_format)
    seen: dict = {}
    original = Figure.savefig

    def spy(self, *a, **k):
        leg = self.axes[0].get_legend()
        seen["labels"] = [t.get_text() for t in leg.get_texts()] if leg else []
        return original(self, *a, **k)

    Figure.savefig = spy
    try:
        IMAGE_BUILDERS["combo"](ctx)
    finally:
        Figure.savefig = original
    assert len(seen["labels"]) == len(set(seen["labels"])), seen["labels"]
