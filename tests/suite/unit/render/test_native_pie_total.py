"""A native pie must draw the whole sample, never whichever group came first.

PowerPoint renders only the first series of a pie, so handing it every classifier
group would produce one group's distribution wearing the whole sample's clothes.
(spec 2026-08-22)
"""
from __future__ import annotations

from reportbuilder.render.native.pie import build_pie
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import make_ctx


def _split_series() -> SeriesResult:
    cats = ("Yes", "No")
    # The FIRST group is lopsided; the Total is even. If the builder grabs the
    # first segment, the drawn values are 90/10 instead of 50/50.
    per_seg = {"Naiset": (90.0, 10.0), "Miehet": (10.0, 90.0), "Total": (50.0, 50.0)}
    cells = {}
    for seg, (a, b) in per_seg.items():
        cells[("Yes", seg)] = Cell(pct=a, count=a, mean=None)
        cells[("No", seg)] = Cell(pct=b, count=b, mean=None)
    return SeriesResult(categories=cats, segments=("Naiset", "Miehet", "Total"),
                        cells=cells,
                        base_n={"Naiset": 100, "Miehet": 100, "Total": 200},
                        statistic="pct")


def test_native_pie_draws_the_total_not_the_first_group():
    _prs, _slide, _slot, ctx = make_ctx("pie", _split_series(),
                                        classifying_var="sex")
    gf = build_pie(ctx)
    plot = gf.chart.plots[0]
    assert len(plot.series) == 1, "a pie must be handed exactly one series"
    assert list(plot.series[0].values) == [50.0, 50.0]
