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


def auto_decimals(values: list[float], statistic: str) -> int:
    """Choose decimal places automatically from value range and statistic (REQ-N-01/02/03).

    pct:   0 when all values are ≥ 10 or fractional parts are negligible;
           1 when any value is < 10 with a non-trivial fraction or the spread
           between adjacent sorted values is < 1.
    mean:  0 if values span a wide, integer-ish range (spread ≥ 5 and fracs trivial);
           1 otherwise (Likert-style or close values).
    count: always 0.
    """
    if statistic == "count":
        return 0
    clean = [float(v) for v in values if v is not None]
    if not clean:
        return 1 if statistic == "mean" else 0
    if statistic == "pct":
        all_large = all(v >= 10.0 for v in clean)
        frac_trivial = all(abs(v % 1) < 0.05 for v in clean)
        if all_large or frac_trivial:
            return 0
        sorted_vals = sorted(clean)
        if len(sorted_vals) > 1:
            min_spread = min(b - a for a, b in zip(sorted_vals, sorted_vals[1:]))
        else:
            min_spread = 1.0
        if any(v < 10.0 for v in clean) or min_spread < 1.0:
            return 1
        return 0
    if statistic == "mean":
        spread = max(clean) - min(clean)
        int_ish = all(abs(v % 1) < 0.1 for v in clean)
        if spread >= 5.0 and int_ish:
            return 0  # wide integer-ish range
        return 1  # Likert-style or close values
    return 0


def format_value(v: float, statistic: str, fmt, all_values: list[float] | None = None) -> str:
    """Format a single data-label value, honouring NumberFormat.mode (REQ-N-01/02/03).

    mode='auto'   → choose decimals from all_values (or [v] if not supplied).
    mode='manual' → use fmt.pct_decimals / fmt.mean_decimals.

    Appends ' %' for pct when show_pct_sign is True.
    """
    show_sign = getattr(fmt, "show_pct_sign", True) if fmt else True
    mode = getattr(fmt, "mode", "auto") if fmt else "auto"

    if mode == "auto":
        vals = list(all_values) if all_values is not None else [float(v)]
        dec = auto_decimals(vals, statistic)
    else:
        if statistic == "pct":
            dec = getattr(fmt, "pct_decimals", 0) if fmt else 0
        elif statistic == "mean":
            dec = getattr(fmt, "mean_decimals", 1) if fmt else 1
        else:
            dec = 0

    if statistic == "pct":
        return f"{v:.{dec}f} %" if show_sign else f"{v:.{dec}f}"
    if statistic == "mean":
        return f"{v:.{dec}f}"
    return f"{v:.0f}"


def fmt_value(v: float, statistic: str, number_format=None) -> str:
    """Legacy label formatter — delegates to format_value (auto mode; single-value context).

    Prefer format_value(v, statistic, fmt, all_values) for correct auto-decimals.
    """
    return format_value(v, statistic, number_format, all_values=[v])


def new_square_figure(ctx):
    """Create a square matplotlib Figure sized to min(slot width, slot height).

    Used by pie, doughnut, and radar builders so the circle is not stretched
    when placed in a landscape slide slot.  Returns (fig, ax) with a cartesian
    Axes (caller replaces ax with a polar Axes if needed).
    """
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    sq = min(w_in, h_in)
    fig, ax = plt.subplots(figsize=(sq, sq), dpi=200)
    fig.patch.set_facecolor(CREAM)
    ax.set_facecolor(CREAM)
    return fig, ax


def place_picture_square(ctx, png_path: str) -> None:
    """Place a square PNG centred in ctx.slot, maintaining a 1:1 aspect ratio.

    Fits the image to the smaller slot dimension and centres it within the slot
    so a circular pie/radar chart is not stretched to oval by the 16:9 slot.
    """
    display_size = min(ctx.slot.width, ctx.slot.height)
    left = ctx.slot.left + (ctx.slot.width - display_size) // 2
    top = ctx.slot.top + (ctx.slot.height - display_size) // 2
    ctx.slide.shapes.add_picture(png_path, left, top, display_size, display_size)


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
