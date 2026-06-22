"""Image-mode radar (spider/polar) chart builder (Task 5.12).

Builder: build_image_radar.

Renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.
"""
from __future__ import annotations

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from reportbuilder.render.image._mpl import (
    render_png, place_picture, series_values,
)

_EMU_PER_IN = 914400.0


def build_image_radar(ctx) -> None:
    """Multi-series radar (polar) chart.

    Creates the figure directly (not via new_figure) in order to attach a
    polar projection subplot, since new_figure produces a cartesian Axes.
    The figure is sized identically to what new_figure would produce.
    """
    cats, segs, data = series_values(ctx.series)

    w_in = max(2.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(1.5, ctx.slot.height / _EMU_PER_IN)
    fig = plt.figure(figsize=(w_in, h_in), dpi=150)
    ax = fig.add_subplot(111, polar=True)

    n_cats = len(cats)
    angles = np.linspace(0, 2 * np.pi, n_cats, endpoint=False)
    # Close the loop
    closed_angles = np.concatenate([angles, [angles[0]]])

    for i, seg in enumerate(segs):
        vals = data[seg]
        closed_vals = list(vals) + [vals[0]]
        ax.plot(
            closed_angles,
            closed_vals,
            label=seg,
            color="#" + ctx.style.color_for(i),
        )
        ax.fill(
            closed_angles,
            closed_vals,
            alpha=0.1,
            color="#" + ctx.style.color_for(i),
        )

    ax.set_xticks(angles)
    ax.set_xticklabels(cats, fontsize=8)

    if ctx.spec.elements.legend and len(segs) > 1:
        ax.legend(fontsize=7, loc="upper right", bbox_to_anchor=(1.3, 1.1))

    png = render_png(fig)
    place_picture(ctx, png)
