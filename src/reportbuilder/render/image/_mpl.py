"""Shared matplotlib helpers for image-mode chart builders (Task 5.11).

Sets the Agg backend at module level before importing pyplot so that callers
can safely import this module in headless/test environments without a display.
"""
from __future__ import annotations
import os
import tempfile
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from reportbuilder.render.house_style import register_fonts, CREAM

_EMU_PER_IN = 914400.0


def new_figure(ctx):
    """Create a matplotlib Figure/Axes sized to ctx.slot, with nSight house style applied.

    Applies cream background and Liberation Sans font (REQ-C-25/27a).
    Minimum size enforced to maintain legibility at any slot dimension.
    """
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    fig, ax = plt.subplots(figsize=(w_in, h_in), dpi=200)
    fig.patch.set_facecolor(CREAM)
    ax.set_facecolor(CREAM)
    return fig, ax


def render_png(fig) -> str:
    """Save figure to a temp PNG file at high quality and close it. Returns the file path."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.04)
    plt.close(fig)
    return path


def place_picture(ctx, png_path: str) -> None:
    """Place png_path onto ctx.slide at ctx.slot geometry via add_picture."""
    ctx.slide.shapes.add_picture(
        png_path,
        ctx.slot.left,
        ctx.slot.top,
        ctx.slot.width,
        ctx.slot.height,
    )


def series_values(series):
    """Decompose a SeriesResult into (cats, segs, data) for chart rendering.

    Returns:
        cats: list of category labels (x-axis / bar groups)
        segs: list of segment labels (series)
        data: dict of seg -> list[float] (one value per category)
    """
    cats = list(series.categories)
    segs = list(series.segments)
    data = {
        seg: [
            float(series.cell(c, seg).value(series.statistic) or 0.0)
            for c in cats
        ]
        for seg in segs
    }
    return cats, segs, data


def colors(ctx, n: int) -> list[str]:
    """Return n matplotlib hex color strings from ctx.style (prepend '#')."""
    return ["#" + ctx.style.color_for(i) for i in range(n)]
