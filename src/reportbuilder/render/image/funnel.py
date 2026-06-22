"""Image-mode funnel chart builder (Task 5.13).

Draws a TRUE funnel silhouette using centered horizontal bars (widest at top,
narrowest at bottom), which is only achievable in image mode.

Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values,
)


def build_image_funnel(ctx) -> None:
    """Centered horizontal bar funnel chart (widest category on top)."""
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]

    fig, ax = new_figure(ctx)

    max_val = max(vals) if vals else 1.0
    color = "#" + ctx.style.color_for(0)

    for i, v in enumerate(vals):
        left = (max_val - v) / 2
        ax.barh(i, v, left=left, color=color)
        if ctx.spec.elements.data_labels:
            ax.annotate(
                f"{v:.0f}",
                xy=(left + v / 2, i),
                ha="center", va="center", fontsize=8, color="white",
            )

    ax.set_yticks(range(len(cats)))
    ax.set_yticklabels(cats, fontsize=8)
    # Invert y-axis so widest bar (index 0) appears at the top
    ax.invert_yaxis()
    ax.set_xlim(0, max_val)
    ax.xaxis.set_visible(False)

    if ctx.spec.elements.title:
        ax.set_title(ctx.title)

    png = render_png(fig)
    place_picture(ctx, png)
