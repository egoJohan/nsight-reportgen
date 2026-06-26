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

from reportbuilder.render.house_style import register_fonts, CREAM, INK, GRIDC

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
    """Return n matplotlib hex color strings from ctx.style (prepend '#').

    Retained for backwards-compatibility; prefer `series_colors(n)` for house style.
    """
    return ["#" + ctx.style.color_for(i) for i in range(n)]


def fmt_value(v: float, statistic: str, number_format=None) -> str:
    """Format a data label value with statistic-appropriate suffix.

    pct  → "86 %"  (REQ-C-24f, show_pct_sign)
    mean → "4.2"   (respects number_format.mean_decimals)
    count / other → "86"
    """
    if statistic == "pct":
        show_sign = getattr(number_format, "show_pct_sign", True) if number_format else True
        return f"{v:.0f} %" if show_sign else f"{v:.0f}"
    if statistic == "mean":
        dec = getattr(number_format, "mean_decimals", 1) if number_format else 1
        return f"{v:.{dec}f}"
    return f"{v:.0f}"


def style_legend(ax, loc: str = "best") -> None:
    """Apply house-style formatting to an axes legend (shared by all image builders).

    White frame, GRIDC edge, INK text, 9.5 pt font.
    """
    from reportbuilder.render.house_style import GRIDC as _GC, INK as _INK
    leg = ax.legend(fontsize=9.5, loc=loc, frameon=True)
    if leg is None:
        return
    leg.get_frame().set_facecolor("#FFFFFF")
    leg.get_frame().set_edgecolor(_GC)
    leg.get_frame().set_linewidth(0.8)
    for t in leg.get_texts():
        t.set_color(_INK)
