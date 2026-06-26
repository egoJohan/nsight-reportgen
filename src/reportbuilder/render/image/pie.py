"""Image-mode pie and doughnut chart builders — nSight house style (REQ-C-24/25/27a).

Builders: build_image_pie, build_image_doughnut.

House style:
- Cream figure background, Liberation Sans font
- Teal ramp for slice colours (single series → TEAL, multi-slice → spread)
- Percentage labels outside each slice (leader lines, INK text, 10 pt)
- No matplotlib title (handled by slide chrome, REQ-D-04)
- Only suitable for single-choice parts-of-whole questions

Each renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values,
)
from reportbuilder.render.house_style import series_colors, INK, MUTED, CREAM


def _pie_autopct(statistic: str):
    """Return an autopct format string or callable for pie/doughnut labels."""
    if statistic == "pct":
        return "%1.0f %%"
    return "%1.0f"


def build_image_pie(ctx) -> None:
    """Single-series pie chart with house style (REQ-C-24b, REQ-C-27a).

    Uses the first segment's values.  Slices are coloured with the teal ramp;
    percentage labels use `autopct` outside each slice with leader lines.
    """
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]
    clrs = series_colors(len(cats))

    fig, ax = new_figure(ctx)
    ax.set_facecolor(CREAM)

    wedges, texts, autotexts = ax.pie(
        vals,
        labels=cats if ctx.spec.elements.axis_names else None,
        colors=clrs,
        autopct=_pie_autopct(ctx.series.statistic),
        pctdistance=0.80,
        startangle=90,
        wedgeprops=dict(linewidth=1.2, edgecolor=CREAM),
    )

    # Style label and pct texts
    for t in texts:
        t.set_fontsize(10.5)
        t.set_color(INK)
    for t in autotexts:
        t.set_fontsize(9.5)
        t.set_fontweight("bold")
        t.set_color(INK)

    png = render_png(fig)
    place_picture(ctx, png)


def build_image_doughnut(ctx) -> None:
    """Single-series doughnut chart with house style (REQ-C-24b, REQ-C-27a).

    Pie with a central hole (width=0.40).  Slices use the teal ramp;
    pct labels sit inside each arc segment.
    """
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]
    clrs = series_colors(len(cats))

    fig, ax = new_figure(ctx)
    ax.set_facecolor(CREAM)

    wedges, texts, autotexts = ax.pie(
        vals,
        labels=cats if ctx.spec.elements.axis_names else None,
        colors=clrs,
        autopct=_pie_autopct(ctx.series.statistic),
        pctdistance=0.75,
        startangle=90,
        wedgeprops=dict(width=0.42, linewidth=1.5, edgecolor=CREAM),
    )

    # Style label and pct texts
    for t in texts:
        t.set_fontsize(10.5)
        t.set_color(INK)
    for t in autotexts:
        t.set_fontsize(9.5)
        t.set_fontweight("bold")
        t.set_color(INK)

    png = render_png(fig)
    place_picture(ctx, png)
