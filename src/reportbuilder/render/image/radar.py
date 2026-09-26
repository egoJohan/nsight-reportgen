"""Image-mode radar (spider/polar) chart builder — nSight house style (REQ-C-24/25/27a).

Builder: build_image_radar.

House style:
- Slide-background bg, Liberation Sans font
- Teal ramp colours per segment (single series → TEAL; multi → spread)
- Filled polygon at 15 % alpha; thick lines at 2.0–2.5 pt
- Grid-tone polar grid lines; no default matplotlib colours
- Legend with house style (ink-tone text) when multi-series
- No matplotlib title (handled by slide chrome, REQ-D-04)

Furniture (ink/muted/grid, figure/axes background) is derived from the
slide's own background via `chart_furniture`/`chart_background` — unchanged on
a light slide, flipped for legibility on a dark one.

Renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.
"""
from __future__ import annotations

import math

import numpy as np
from matplotlib import patheffects
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

from reportbuilder.render.image._mpl import (
    _remember_font,chart_accent,
    render_png, place_picture_square, series_label, series_values, place_total,
    colours_by_series, coded_order,
    style_legend, wrap_label,
    chart_background, chart_furniture, _value_axis,
)
from reportbuilder.render.house_style import register_fonts, series_colors
from reportbuilder.render.image._mpl import template_palette

_EMU_PER_IN = 914400.0


def _ring_label_candidates(angles: list[float], segs, data) -> list[float]:
    """Gap midpoints between spokes, the emptiest of DATA first.

    Between spokes rather than on one, because a spoke line is drawn at its own
    angle and the numbers would lie along it. Each gap is scored by how far the
    data reaches on the two spokes bounding it, across every series, since any
    of them can cross the numbers. Ties keep spoke order, so a flat radar is
    deterministic.
    """
    n = len(angles)
    if n < 2:
        return [22.5]
    reach = []
    for i in range(n):
        vals = [data[seg][i] for seg in segs
                if data.get(seg) and data[seg][i] is not None]
        reach.append(max(vals) if vals else 0.0)
    step = 360.0 / n
    scored = []
    for i in range(n):
        scored.append((max(reach[i], reach[(i + 1) % n]), i,
                       (math.degrees(angles[i]) + step / 2.0) % 360.0))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [mid for _score, _i, mid in scored]


def _rings_cross_a_name(fig, ax) -> bool:
    """Whether any ring number is printed over a spoke name, as drawn.

    Both are unrotated on a radar, so a plain box intersection is the right
    instrument — unlike a rotated tick label, whose axis-aligned box is far
    wider than its ink.
    """
    r = fig.canvas.get_renderer()
    rings = [t.get_window_extent(r) for t in ax.get_yticklabels() if t.get_text()]
    names = [t.get_window_extent(r) for t in ax.get_xticklabels() if t.get_text()]
    # And the points' own values, since radars print them (2026-09-26): the
    # scale printed "40" onto "25 %". A radar without values is unaffected.
    from reportbuilder.render.image._mpl import VALUE_GID
    names += [t.get_window_extent(r) for t in ax.texts
              if t.get_gid() == VALUE_GID and t.get_visible()]
    for a in rings:
        for b in names:
            if (min(a.x1, b.x1) - max(a.x0, b.x0) > 0.5
                    and min(a.y1, b.y1) - max(a.y0, b.y0) > 0.5):
                return True
    return False


def _place_ring_labels(fig, ax, angles: list[float], segs, data,
                       tries: int = 6) -> float:
    """Put the ring numbers where they cross neither the polygon nor a name.

    Emptiest of data is where they belong, but empty of data is not empty: a
    spoke whose name wraps to five lines owns the perimeter beside it, and on
    HolidayClub's var8 the two spokes the data reaches least far on are exactly
    the two carrying the longest names — so the gap chosen for being clear of
    the polygon printed "100" straight onto "Musiikkiesitykset tai muu
    kulttuuritarjonta".

    So the candidates are tried in that order and MEASURED, and the first that
    crosses nothing wins. A radar whose first choice is already clear pays one
    extra draw; one that is never clear keeps the emptiest gap, which is the
    best of a bad set rather than an arbitrary one.
    """
    candidates = _ring_label_candidates(angles, segs, data)
    for angle in candidates[:max(1, tries)]:
        ax.set_rlabel_position(angle)
        fig.canvas.draw()
        if not _rings_cross_a_name(fig, ax):
            return angle
    ax.set_rlabel_position(candidates[0])
    return candidates[0]


#: The most groups a radar prints its values for.
_MAX_NUMBERED = 3


def _readable(colour, ink):
    """The group's colour for its numbers, unless it is too pale to read on the
    slide — then the ink colour."""
    from matplotlib.colors import to_rgb

    try:
        r, g, b = to_rgb(colour)
    except ValueError:
        return ink
    return ink if 0.299 * r + 0.587 * g + 0.114 * b > 0.72 else colour


def _point_values(fig, ax, ctx, angles, segs, data, clrs, all_vals, r_max, ink,
                  bg="#FFFFFF") -> bool:
    """Each point's value beside it, in its group's colour. True if drawn.

    Placed where it is measured to fit, in display space: for each value the
    positions are tried in order — just outside the point along its spoke, to
    either side of the point, just inside it — and the first that overlaps no
    value already placed, no spoke name and stays inside the ring wins. Pushing
    values outward along the spoke alone packed wide numbers end to end on a
    horizontal spoke and ran the last into the spoke's name. If any value finds
    no place, none are drawn: a radar with some numbers and not others reads as
    a fault. The caller tells the author.
    """
    from reportbuilder.render.image._mpl import VALUE_GID, format_value
    from reportbuilder.render.image.bars import _measure_max_label_width_in

    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    dpi = fig.dpi
    names = [t.get_window_extent(rend) for t in ax.get_xticklabels() if t.get_text()]
    cx, cy = ax.transData.transform((0.0, 0.0))
    ring_px = math.hypot(*(np.array(ax.transData.transform((0.0, r_max))) - (cx, cy)))
    radius_in = ring_px / dpi
    # Sized to the radar: 8pt on a large one, down to 6pt on a small one.
    pt = max(6.0, min(8.0, radius_in * 3.2))
    gap = 2.5 / 72.0 * dpi
    h = pt / 72.0 * dpi * 1.15

    def free(box, placed):
        x0, y0, x1, y1 = box
        # Its centre within the ring: the names are outside it and are checked
        # as boxes below, which is the real guard.
        if math.hypot((x0 + x1) / 2 - cx, (y0 + y1) / 2 - cy) > ring_px:
            return False
        for o in placed + [(n.x0, n.y0, n.x1, n.y1) for n in names]:
            if min(x1, o[2]) - max(x0, o[0]) > 0 and min(y1, o[3]) - max(y0, o[1]) > 0:
                return False
        return True

    chosen, placed = [], []
    for k, ang in enumerate(angles):
        # Highest value first: it is the one nearest the ring, with least room.
        order = sorted((i for i, seg in enumerate(segs) if data[seg][k] is not None),
                       key=lambda i: -data[segs[i]][k])
        for i in order:
            v = data[segs[i]][k]
            text = format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals)
            w = _measure_max_label_width_in([text], pt) * dpi
            px, py = ax.transData.transform((ang, v))
            ux, uy = math.cos(ang), math.sin(ang)          # outward on screen
            qx, qy = -uy, ux                               # across the spoke
            along = abs(ux) * w / 2 + abs(uy) * h / 2
            across = abs(qx) * w / 2 + abs(qy) * h / 2
            out_ = gap + along
            side = gap + across
            spots = [(px + ux * out_, py + uy * out_),
                     (px + qx * side, py + qy * side),
                     (px - qx * side, py - qy * side),
                     (px + ux * out_ + qx * side, py + uy * out_ + qy * side),
                     (px + ux * out_ - qx * side, py + uy * out_ - qy * side),
                     (px - ux * out_, py - uy * out_),
                     (px + qx * 2 * side, py + qy * 2 * side),
                     (px - qx * 2 * side, py - qy * 2 * side),
                     (px - ux * out_ + qx * side, py - uy * out_ + qy * side),
                     (px - ux * out_ - qx * side, py - uy * out_ - qy * side)]
            for sx, sy in spots:
                box = (sx - w / 2, sy - h / 2, sx + w / 2, sy + h / 2)
                if free(box, placed):
                    placed.append(box)
                    chosen.append((sx, sy, text, i))
                    break
            else:
                return False
    inv = ax.transData.inverted()
    for sx, sy, text, i in chosen:
        th, rr = inv.transform((sx, sy))
        t = ax.text(th, rr, text, ha="center", va="center", fontsize=pt, fontweight="bold",
                    color=_readable(clrs[i], ink), zorder=6, gid=VALUE_GID, clip_on=False)
        # A thin outline in the slide's own background colour, so a number
        # that lands on the polygon's edge is not crossed out by it.
        t.set_path_effects([patheffects.withStroke(linewidth=2.2, foreground=bg)])
    return True


def build_image_radar(ctx) -> None:
    """Multi-series radar (polar) chart with nSight house style.

    Creates the figure directly (not via new_figure) so a polar projection
    subplot can be attached — new_figure produces a cartesian Axes.
    The figure is sized identically to what new_figure would produce.
    REQ-C-24b/f, REQ-C-27a.
    """
    register_fonts()
    cats, segs, data = series_values(ctx.series)
    # A radar's rings have no top or bottom; its legend has a first and a last.
    default_segs, segs = coded_order(ctx.series, segs), place_total(segs, getattr(ctx.spec, "total_position", "auto"))
    clrs = colours_by_series(series_colors(len(segs), palette=template_palette(ctx),
                                           accent=chart_accent(ctx)),
                             default_segs, segs)
    bg = chart_background(ctx)
    ink, muted, grid = chart_furniture(ctx)

    # Square figure: min slot dimension → circular polar axes, not oval
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    sq = min(w_in, h_in)
    fig = Figure(figsize=(sq, sq), dpi=200)
    _remember_font(fig, ctx)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(bg)
    ax = fig.add_subplot(111, polar=True)
    ax.set_facecolor(bg)

    n_cats = len(cats)
    angles = np.linspace(0, 2 * np.pi, n_cats, endpoint=False).tolist()
    # Close the loop for a connected polygon
    closed_angles = angles + [angles[0]]

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=100.0)
    # The shared axis rule, not a copy of its percentage half. `min(100.0, …)`
    # capped every statistic, so a radar of COUNTS was drawn against a 0..100
    # scale and its polygon left the plot — the same defect reported on the line
    # chart, here simply never tried. A small integer scale (a 1-5 rating) still
    # gets its own ticks below. (Johan, 2026-09-16)
    r_max, r_scale_ticks = _value_axis(max_val, ctx.series.statistic)

    for i, seg in enumerate(segs):
        vals = data[seg]
        closed_vals = list(vals) + [vals[0]]
        ax.plot(
            closed_angles, closed_vals,
            label=series_label(ctx, seg), color=clrs[i],
            linewidth=2.4 if len(segs) == 1 else 2.0,
            zorder=4,
        )
        ax.fill(closed_angles, closed_vals, alpha=0.15, color=clrs[i], zorder=3)

    # Spoke labels — wrap long category labels onto multiple lines (and
    # force-break pathological unbroken long words) so they don't overlap the
    # polygon or run off the figure. Shrink the font a touch as categories grow.
    fs = 10.0 if n_cats <= 8 else (9.0 if n_cats <= 12 else 8.0)
    ax.set_xticks(angles)
    ax.set_xticklabels([wrap_label(c, 16) for c in cats], fontsize=fs, color=ink)
    ax.tick_params(axis="x", pad=10)

    # Radial grid
    ax.set_ylim(0, r_max)
    # Radial ticks adapt to the value range: pct uses the 0–100 scale; a mean
    # radar (e.g. a 1–5 rating comparison) uses integer scale points.
    if r_max <= 12:
        r_ticks = [v for v in range(1, int(r_max) + 1)]
    else:
        r_ticks = [v for v in r_scale_ticks if 0 < v <= r_max]
    ax.set_yticks(r_ticks)
    ax.set_yticklabels(
        [str(int(v)) if float(v).is_integer() else f"{v:g}" for v in r_ticks],
        fontsize=8.0, color=muted)
    # The value at each point — "Voisiko varmistaa, että kaikissa kaaviotyypeissä
    # näkyy prosentit" (2026-09-25): a radar printed none. Up to three groups;
    # with more they bury the shape a radar is read by. (Johan, 2026-09-26)
    if getattr(ctx.spec.elements, "data_labels", True) and 0 < len(segs) <= _MAX_NUMBERED:
        if not _point_values(fig, ax, ctx, angles, segs, data, clrs, all_vals, r_max, ink, bg):
            from reportbuilder.render.base import note
            note(ctx, "unlabelled", n_cats)

    _place_ring_labels(fig, ax, angles, segs, data)
    ax.grid(color=grid, linewidth=0.8)
    ax.spines["polar"].set_color("#C9C1B4")
    ax.spines["polar"].set_linewidth(1.0)

    if ctx.spec.elements.legend and len(segs) > 1:
        # Place the entity legend BELOW the chart so it never covers the
        # perimeter attribute labels that ring the radar.
        leg = ax.legend(
            loc="upper center", bbox_to_anchor=(0.5, -0.06),
            ncol=min(len(segs), 4), frameon=False, fontsize=9.0,
            handlelength=1.1, columnspacing=1.4, handletextpad=0.5,
        )
        if leg is not None:
            for t in leg.get_texts():
                t.set_color(ink)

    png = render_png(fig)
    place_picture_square(ctx, png)
