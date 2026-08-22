"""A funnel split by a background variable draws one funnel per group."""
from __future__ import annotations

from reportbuilder.render.charts.funnel import suitability
from reportbuilder.render.image._mpl import chart_background, chart_furniture, new_figure
from reportbuilder.render.image.funnel import _draw_one_funnel, build_image_funnel
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


def test_narrow_bar_label_moves_outside_and_recolors_ink():
    """A stage a fraction of the widest one — the case a panel row (a third of
    the old figure width) makes newly reachable — must not render its label as
    illegible white-on-white outside the bar's own teal fill.

    A wide bar (the funnel's own top stage) must render exactly as it always
    has: centred inside the bar, white."""
    _prs, _slide, _slot, ctx = make_ctx("funnel", _descending_split())
    fig, ax = new_figure(ctx)
    bg = chart_background(ctx)
    ink, _muted, _grid = chart_furniture(ctx)

    cats = ("Tuntee", "Harkitsee", "Ostanut")
    vals = [90.0, 60.0, 2.0]  # the last stage is a sliver next to the first
    _draw_one_funnel(ax, cats, vals, ctx, bg, ink)

    n = len(cats)
    value_labels = ax.texts[:n]  # drawn before the category labels, in order

    max_val = max(vals)
    wide_left = (max_val - vals[0]) / 2
    wide_right = wide_left + vals[0]
    wide_label = value_labels[0]
    wx, _wy = wide_label.get_position()
    assert wide_left < wx < wide_right, "wide bar's label must stay centred inside it"
    assert wide_label.get_color() == "#FFFFFF"
    assert wide_label.get_ha() == "center"

    narrow_left = (max_val - vals[-1]) / 2
    narrow_right = narrow_left + vals[-1]
    narrow_label = value_labels[-1]
    nx, _ny = narrow_label.get_position()
    assert nx > narrow_right, "label too wide for its bar must move outside it"
    assert narrow_label.get_color() == ink
    assert narrow_label.get_ha() == "left"
