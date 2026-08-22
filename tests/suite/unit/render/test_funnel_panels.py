"""A funnel split by a background variable draws one funnel per group."""
from __future__ import annotations

from reportbuilder.render.charts.funnel import suitability
from reportbuilder.render.image.funnel import build_image_funnel
from reportbuilder.stats.series import Cell, SeriesResult

from suite._helpers import assert_single_picture, make_ctx
from suite.unit.render._builders import q


def _descending_split() -> SeriesResult:
    cats = ("Tuntee", "Harkitsee", "Ostanut")
    cells = {}
    for seg, scale in (("Naiset", 1.0), ("Miehet", 0.8), ("Total", 0.9)):
        for c, v in zip(cats, (90.0, 60.0, 30.0)):
            cells[(c, seg)] = Cell(pct=v * scale, count=v * scale, mean=None)
    return SeriesResult(categories=cats, segments=("Naiset", "Miehet", "Total"),
                        cells=cells,
                        base_n={"Naiset": 100, "Miehet": 100, "Total": 200},
                        statistic="pct")


def test_split_funnel_is_still_offered():
    # The old rule scored any multi-series down to 0.30, which would have buried
    # the funnel in the picker the moment a classifier was chosen.
    assert suitability(q(), _descending_split()) == 0.85


def test_split_funnel_places_one_picture():
    _prs, slide, slot, ctx = make_ctx("funnel", _descending_split(),
                                      classifying_var="sex")
    build_image_funnel(ctx)
    assert_single_picture(slide, slot)
