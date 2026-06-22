"""Image-mode scatter (XY) chart builder (Task 5.12).

Builder: build_image_scatter.

Renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None. Requires ctx.spec.scatter_xy to be set.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values,
)


def build_image_scatter(ctx) -> None:
    """XY scatter plot. Requires ctx.spec.scatter_xy = (x_seg, y_seg).

    Raises ValueError if scatter_xy is None.
    """
    if ctx.spec.scatter_xy is None:
        raise ValueError(
            "scatter requires scatter_xy (two numeric axis segments)"
        )

    x_seg, y_seg = ctx.spec.scatter_xy
    cats, segs, data = series_values(ctx.series)
    xs = data[x_seg]
    ys = data[y_seg]

    fig, ax = new_figure(ctx)
    ax.scatter(xs, ys, color="#" + ctx.style.color_for(0))

    if ctx.spec.elements.data_labels:
        for cat, x, y in zip(cats, xs, ys):
            ax.annotate(
                cat,
                xy=(x, y),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=7,
            )

    if ctx.spec.elements.axis_names:
        ax.set_xlabel(x_seg, fontsize=8)
        ax.set_ylabel(y_seg, fontsize=8)

    if ctx.spec.elements.title:
        ax.set_title(ctx.title)

    png = render_png(fig)
    place_picture(ctx, png)
