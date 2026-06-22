"""Image-mode pie and doughnut chart builders (Task 5.12).

Builders: build_image_pie, build_image_doughnut.

Each renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values, colors,
)


def build_image_pie(ctx) -> None:
    """Single-series pie chart. Uses the first segment's values."""
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]
    fig, ax = new_figure(ctx)
    ax.pie(
        vals,
        labels=cats if ctx.spec.elements.axis_names else None,
        colors=colors(ctx, len(cats)),
        autopct="%1.0f%%" if ctx.spec.elements.data_labels else None,
    )
    if ctx.spec.elements.title:
        ax.set_title(ctx.title)
    png = render_png(fig)
    place_picture(ctx, png)


def build_image_doughnut(ctx) -> None:
    """Single-series doughnut chart (pie with a hole). Uses the first segment's values."""
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]
    fig, ax = new_figure(ctx)
    ax.pie(
        vals,
        labels=cats if ctx.spec.elements.axis_names else None,
        colors=colors(ctx, len(cats)),
        autopct="%1.0f%%" if ctx.spec.elements.data_labels else None,
        wedgeprops=dict(width=0.4),
    )
    if ctx.spec.elements.title:
        ax.set_title(ctx.title)
    png = render_png(fig)
    place_picture(ctx, png)
