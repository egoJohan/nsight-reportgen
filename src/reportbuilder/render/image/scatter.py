"""Image-mode scatter (XY) chart builder — nSight house style (REQ-C-24/25/27a).

Builder: build_image_scatter.

House style:
- Cream bg, Liberation Sans, TEAL scatter points
- INK bold category labels near each point
- Bottom + left spines (house style), GRIDC gridlines
- No matplotlib title (handled by slide chrome, REQ-D-04)

Renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None. Requires ctx.spec.scatter_xy to be set.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values,
)
from reportbuilder.render.house_style import TEAL, INK, MUTED, GRIDC


def build_image_scatter(ctx) -> None:
    """XY scatter plot with house style. Requires ctx.spec.scatter_xy = (x_seg, y_seg).

    Raises ValueError if scatter_xy is None.  REQ-C-24b/f, REQ-C-27a.
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
    ax.scatter(xs, ys, color=TEAL, s=70, edgecolors="#FFFFFF", linewidths=0.8, zorder=3)

    if ctx.spec.elements.data_labels:
        for cat, x, y in zip(cats, xs, ys):
            ax.annotate(
                cat,
                xy=(x, y),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=9.5, color=INK,
            )

    if ctx.spec.elements.axis_names:
        ax.set_xlabel(x_seg, fontsize=10.5, color=INK)
        ax.set_ylabel(y_seg, fontsize=10.5, color=INK)

    # House-style spines
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color("#C9C1B4")
    ax.spines["left"].set_linewidth(1.0)

    ax.tick_params(axis="both", length=0)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=9.5)

    # Light grid
    ax.grid(color=GRIDC, linewidth=0.7, zorder=0)

    png = render_png(fig)
    place_picture(ctx, png)
