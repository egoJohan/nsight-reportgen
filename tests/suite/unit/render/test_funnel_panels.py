"""A funnel split by a background variable draws one funnel per group."""
from __future__ import annotations

from dataclasses import dataclass

import pytest

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


def _split(scales: dict[str, float], *, cats=("Tuntee", "Harkitsee", "Ostanut"),
           base=100) -> SeriesResult:
    """One funnel per key, each a 90/60/30 descent scaled by its own factor."""
    segs = (*scales, "Total")
    cells = {}
    for seg in segs:
        scale = scales.get(seg, 1.0)
        for c, v in zip(cats, (90.0, 60.0, 30.0)):
            cells[(c, seg)] = Cell(pct=v * scale, count=v * scale, mean=None)
    return SeriesResult(categories=cats, segments=segs, cells=cells,
                        base_n={s: base for s in segs}, statistic="pct")


@dataclass
class _Panel:
    """What one drawn funnel panel looked like, sampled off its Axes."""

    ylim: tuple[float, float]
    xlim: tuple[float, float]
    axes_width: float          # fraction of the figure width
    bar_widths: tuple[float, ...]
    texts: tuple[str, ...]


def _panels(series, **spec_kw) -> list[_Panel]:
    """Run `build_image_funnel` and sample every axes it drew on.

    The figure is cleared by `render_png` on its way out, so the sample is taken
    inside a `render_png` wrapper — the last moment the artists still exist."""
    import reportbuilder.render.image.funnel as mod

    _prs, _slide, _slot, ctx = make_ctx("funnel", series, **spec_kw)
    sampled: list[_Panel] = []
    real_png = mod.render_png

    def sampling_render_png(fig):
        for ax in fig.axes:
            sampled.append(_Panel(
                ylim=ax.get_ylim(), xlim=ax.get_xlim(),
                axes_width=ax.get_position().width,
                bar_widths=tuple(p.get_width() for p in ax.patches),
                texts=tuple(t.get_text() for t in ax.texts),
            ))
        return real_png(fig)

    mod.render_png = sampling_render_png
    try:
        build_image_funnel(ctx)
    finally:
        mod.render_png = real_png
    return sampled


def _first_bar_width(panel: _Panel) -> float:
    """Width of the top (widest) stage's bar, in data units."""
    return max(panel.bar_widths)


def test_funnel_points_the_same_way_at_every_panel_count():
    """The widest stage is on TOP — whatever the panel count.

    `invert_yaxis()` TOGGLES, and the panel grid shares one y-axis, so one call
    per panel cancelled itself on an EVEN count: two groups (a split by gender,
    the likeliest one there is) rendered the funnel upside down while three
    groups happened to come out right. A test at three groups alone passes by
    parity and proves nothing, so assert 1, 2 AND 3.
    """
    cases = {
        "unsplit": (_split({}), {}),
        "two": (_split({"Naiset": 1.0, "Miehet": 0.6}),
                {"classifying_var": "sex"}),
        "three": (_split({"Naiset": 1.0, "Miehet": 0.6, "Muut": 0.8}),
                  {"classifying_var": "sex"}),
    }
    for name, (series, kw) in cases.items():
        panels = _panels(series, **kw)
        assert panels, name
        for p in panels:
            bottom, top = p.ylim
            assert bottom > top, (
                f"{name}: y-axis must run downwards (widest stage on top), "
                f"got {p.ylim}")


def test_funnel_panels_share_one_bar_scale():
    """Two groups of different magnitude must not draw identical silhouettes.

    Each panel used to rescale to its own maximum, so 90/60/30 and 45/30/15 came
    out as the same funnel — the comparison the split exists for, silently
    destroyed."""
    panels = _panels(_split({"Naiset": 1.0, "Miehet": 0.5}),
                     classifying_var="sex")
    assert len(panels) == 2
    wide, narrow = (_first_bar_width(p) for p in panels)
    assert narrow == pytest.approx(wide / 2, rel=1e-6), (
        f"first-stage bars must differ with the data: {wide} vs {narrow}")

    # Same data units AND the same data-units-per-figure-width in every panel =>
    # comparable on screen, not just in data space.
    def _px_per_unit(p: _Panel) -> float:
        return p.axes_width / (p.xlim[1] - p.xlim[0])

    assert _px_per_unit(panels[1]) == pytest.approx(_px_per_unit(panels[0]),
                                                    rel=1e-6)


def test_unsplit_funnel_scale_is_its_own_maximum():
    """One panel: the shared max IS its own max, so nothing about the un-split
    funnel moves."""
    panels = _panels(_split({}))
    assert len(panels) == 1
    assert _first_bar_width(panels[0]) == pytest.approx(90.0)
    assert panels[0].xlim[1] == pytest.approx(90.0 * 2.05)


def test_stage_labels_are_drawn_once_per_row_not_once_per_panel():
    """Three copies of long Finnish scale labels would leave each funnel about a
    sixth of the slide. The labels belong to the ROW, on its right edge."""
    panels = _panels(_split({"Naiset": 1.0, "Miehet": 0.6, "Muut": 0.8}),
                     classifying_var="sex")
    assert len(panels) == 3
    for cat in ("Tuntee", "Harkitsee", "Ostanut"):
        hits = [i for i, p in enumerate(panels)
                if any(cat in t for t in p.texts)]
        assert hits == [len(panels) - 1], (
            f"{cat} drawn on panels {hits}, want only the rightmost")

    # The panels that no longer carry labels reclaim that reserved width.
    assert panels[0].xlim[1] < panels[-1].xlim[1]


def test_unsplit_funnel_still_draws_every_stage_label():
    panels = _panels(_split({}))
    for cat in ("Tuntee", "Harkitsee", "Ostanut"):
        assert any(cat in t for t in panels[0].texts)
