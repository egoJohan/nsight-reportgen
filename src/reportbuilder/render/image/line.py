"""Image-mode line chart builder (Task 5.11).

Builder: build_image_line — one line per segment.
Returns None.
"""
from __future__ import annotations
from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values, colors,
)


def build_image_line(ctx) -> None:
    """Line chart: one line per segment, x-axis = categories."""
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    clrs = colors(ctx, len(segs))

    x = list(range(len(cats)))

    for i, seg in enumerate(segs):
        vals = data[seg]
        ax.plot(x, vals, marker="o", label=seg, color=clrs[i])
        if ctx.spec.elements.data_labels:
            for xi, v in zip(x, vals):
                ax.annotate(
                    f"{v:.0f}",
                    xy=(xi, v),
                    xytext=(0, 4),
                    textcoords="offset points",
                    ha="center", va="bottom", fontsize=7,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=8)
    if ctx.spec.elements.title:
        ax.set_title("")
    if ctx.spec.elements.legend and len(segs) > 1:
        ax.legend(fontsize=7)

    png = render_png(fig)
    place_picture(ctx, png)


# Register in IMAGE_BUILDERS
from reportbuilder.render.image import IMAGE_BUILDERS  # noqa: E402
IMAGE_BUILDERS["line"] = build_image_line
