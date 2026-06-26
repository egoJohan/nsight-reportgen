"""Image-mode pie and doughnut chart builders — nSight house style (REQ-C-24/25/27a).

Builders: build_image_pie, build_image_doughnut.

House style:
- Cream figure background, Liberation Sans font
- Teal ramp for slice colours (single series → TEAL, multi-slice → spread)
- Percentage labels outside each slice (leader lines, INK text, 10 pt)
- No matplotlib title (handled by slide chrome, REQ-D-04)
- Only suitable for single-choice parts-of-whole questions

Circular aspect: figures are rendered square (min slot dimension) and placed
centred in the slot so the pie is not stretched oval by a 16:9 layout.

Each renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from reportbuilder.render.image._mpl import (
    render_png, place_picture_square, series_values, format_value,
)
from reportbuilder.render.house_style import (
    register_fonts, series_colors, INK, MUTED, CREAM,
)
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL

_EMU_PER_IN = 914400.0


def _pie_autopct_fn(all_vals: list[float], statistic: str, fmt):
    """Return an autopct callable that uses format_value for auto/manual decimals."""
    def _fn(pct: float) -> str:
        return format_value(pct, statistic, fmt, all_vals)
    return _fn


def _make_square_fig_ax(ctx):
    """Create a square figure/axes sized to min(slot width, slot height)."""
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    sq = min(w_in, h_in)
    fig, ax = plt.subplots(figsize=(sq, sq), dpi=200)
    fig.patch.set_facecolor(CREAM)
    ax.set_facecolor(CREAM)
    return fig, ax


def build_image_pie(ctx) -> None:
    """Single-series pie chart with house style (REQ-C-24b, REQ-C-27a).

    Uses the first segment's values.  Slices are coloured with the teal ramp;
    percentage labels use autopct outside each slice.  The figure is rendered
    square and centred in the slot so the pie is circular, not oval.
    The "Not answered" slice is rendered in MUTED grey (R4.2).
    """
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]
    clrs = series_colors(len(cats))
    # R4.2: override "Not answered" slice colour with MUTED grey.
    clrs = [MUTED if c == NOT_ANSWERED_LABEL else clr for c, clr in zip(cats, clrs)]

    fig, ax = _make_square_fig_ax(ctx)

    wedges, texts, autotexts = ax.pie(
        vals,
        labels=cats if ctx.spec.elements.axis_names else None,
        colors=clrs,
        autopct=_pie_autopct_fn(vals, ctx.series.statistic, ctx.spec.number_format),
        pctdistance=0.80,
        startangle=90,
        wedgeprops=dict(linewidth=1.2, edgecolor=CREAM),
    )
    ax.set_aspect("equal")

    # Style label and pct texts
    for t in texts:
        t.set_fontsize(10.5)
        t.set_color(INK)
    for t in autotexts:
        t.set_fontsize(9.5)
        t.set_fontweight("bold")
        t.set_color(INK)

    png = render_png(fig)
    place_picture_square(ctx, png)


def build_image_doughnut(ctx) -> None:
    """Single-series doughnut chart with house style (REQ-C-24b, REQ-C-27a).

    Pie with a central hole (width=0.40).  Slices use the teal ramp;
    pct labels sit inside each arc segment.  Rendered square and centred.
    The "Not answered" slice is rendered in MUTED grey (R4.2).
    """
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]
    clrs = series_colors(len(cats))
    # R4.2: override "Not answered" slice colour with MUTED grey.
    clrs = [MUTED if c == NOT_ANSWERED_LABEL else clr for c, clr in zip(cats, clrs)]

    fig, ax = _make_square_fig_ax(ctx)

    wedges, texts, autotexts = ax.pie(
        vals,
        labels=cats if ctx.spec.elements.axis_names else None,
        colors=clrs,
        autopct=_pie_autopct_fn(vals, ctx.series.statistic, ctx.spec.number_format),
        pctdistance=0.75,
        startangle=90,
        wedgeprops=dict(width=0.42, linewidth=1.5, edgecolor=CREAM),
    )
    ax.set_aspect("equal")

    # Style label and pct texts
    for t in texts:
        t.set_fontsize(10.5)
        t.set_color(INK)
    for t in autotexts:
        t.set_fontsize(9.5)
        t.set_fontweight("bold")
        t.set_color(INK)

    png = render_png(fig)
    place_picture_square(ctx, png)
