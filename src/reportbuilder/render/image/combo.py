"""Image-mode combo chart builder (Task 5.13).

Renders bars on the primary y-axis (first segment) and a line on the secondary
y-axis via twinx (second segment). Falls back to bars-only if only 1 segment
is present.

Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values,
)


def build_image_combo(ctx) -> None:
    """Combo chart: bars (primary y) + line (secondary y via twinx)."""
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)

    color0 = "#" + ctx.style.color_for(0)
    ax.bar(cats, data[segs[0]], color=color0, label=segs[0])

    if len(segs) >= 2:
        color1 = "#" + ctx.style.color_for(1)
        ax2 = ax.twinx()
        ax2.plot(cats, data[segs[1]], color=color1, marker="o", label=segs[1])
        if ctx.spec.elements.legend:
            # Combine legends from both axes
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2, fontsize=7)
    else:
        if ctx.spec.elements.legend:
            ax.legend(fontsize=7)

    if ctx.spec.elements.title:
        ax.set_title(ctx.title)

    png = render_png(fig)
    place_picture(ctx, png)
