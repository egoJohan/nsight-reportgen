"""Image-mode radar (spider/polar) chart builder — nSight house style (REQ-C-24/25/27a).

Builder: build_image_radar.

House style:
- Cream figure/axes background, Liberation Sans font
- Teal ramp colours per segment (single series → TEAL; multi → spread)
- Filled polygon at 15 % alpha; thick lines at 2.0–2.5 pt
- GRIDC polar grid lines; no default matplotlib colours
- Legend with house style (INK text, GRIDC frame) when multi-series
- No matplotlib title (handled by slide chrome, REQ-D-04)

Renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.
"""
from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

from reportbuilder.render.image._mpl import (
    render_png, place_picture_square, series_values, style_legend, wrap_label,
)
from reportbuilder.render.house_style import (
    register_fonts, series_colors, CREAM, INK, MUTED, GRIDC,
)

_EMU_PER_IN = 914400.0


def build_image_radar(ctx) -> None:
    """Multi-series radar (polar) chart with nSight house style.

    Creates the figure directly (not via new_figure) so a polar projection
    subplot can be attached — new_figure produces a cartesian Axes.
    The figure is sized identically to what new_figure would produce.
    REQ-C-24b/f, REQ-C-27a.
    """
    register_fonts()
    cats, segs, data = series_values(ctx.series)
    clrs = series_colors(len(segs))

    # Square figure: min slot dimension → circular polar axes, not oval
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    sq = min(w_in, h_in)
    fig = Figure(figsize=(sq, sq), dpi=200)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(CREAM)
    ax = fig.add_subplot(111, polar=True)
    ax.set_facecolor(CREAM)

    n_cats = len(cats)
    angles = np.linspace(0, 2 * np.pi, n_cats, endpoint=False).tolist()
    # Close the loop for a connected polygon
    closed_angles = angles + [angles[0]]

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=100.0)
    r_max = min(100.0, max_val * 1.15)

    for i, seg in enumerate(segs):
        vals = data[seg]
        closed_vals = list(vals) + [vals[0]]
        ax.plot(
            closed_angles, closed_vals,
            label=seg, color=clrs[i],
            linewidth=2.4 if len(segs) == 1 else 2.0,
            zorder=4,
        )
        ax.fill(closed_angles, closed_vals, alpha=0.15, color=clrs[i], zorder=3)

    # Spoke labels — wrap long category labels onto multiple lines (and
    # force-break pathological unbroken long words) so they don't overlap the
    # polygon or run off the figure. Shrink the font a touch as categories grow.
    fs = 10.0 if n_cats <= 8 else (9.0 if n_cats <= 12 else 8.0)
    ax.set_xticks(angles)
    ax.set_xticklabels([wrap_label(c, 16) for c in cats], fontsize=fs, color=INK)
    ax.tick_params(axis="x", pad=10)

    # Radial grid
    ax.set_ylim(0, r_max)
    r_ticks = [v for v in [20, 40, 60, 80, 100] if v <= r_max]
    ax.set_yticks(r_ticks)
    ax.set_yticklabels([str(v) for v in r_ticks], fontsize=8.0, color=MUTED)
    ax.grid(color=GRIDC, linewidth=0.8)
    ax.spines["polar"].set_color("#C9C1B4")
    ax.spines["polar"].set_linewidth(1.0)

    if ctx.spec.elements.legend and len(segs) > 1:
        style_legend(ax, loc="upper right")

    png = render_png(fig)
    place_picture_square(ctx, png)
