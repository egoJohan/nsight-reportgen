"""Shared matplotlib helpers for image-mode chart builders (Task 5.11).

Sets the Agg backend at module level before importing pyplot so that callers
can safely import this module in headless/test environments without a display.
"""
from __future__ import annotations
import os
import tempfile
import textwrap
import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

from reportbuilder.render.house_style import register_fonts, CREAM, INK, GRIDC, MUTED


def _new_agg_figure(w_in: float, h_in: float, dpi: int = 200) -> Figure:
    """Create a standalone Agg Figure (OO API — NOT pyplot).

    Chart rendering runs on FastAPI's threadpool, so figures are created and
    destroyed concurrently across threads. The pyplot interface (the global Gcf
    figure manager) is not thread-safe; using Figure()+FigureCanvasAgg keeps each
    figure entirely local to its thread, eliminating that race."""
    fig = Figure(figsize=(w_in, h_in), dpi=dpi)
    FigureCanvasAgg(fig)
    return fig

_EMU_PER_IN = 914400.0


def force_break_token(token: str, width: int) -> list[str]:
    """Break a single word longer than *width* into width-sized chunks.

    Last-resort splitting so a pathological unbroken long word (e.g. erroneous
    survey data with no spaces) cannot overflow the chart bounds. Normal words
    shorter than *width* are returned unchanged.
    """
    if len(token) <= width:
        return [token]
    return [token[i:i + width] for i in range(0, len(token), width)]


def wrap_label(text: str, width: int) -> str:
    """Wrap *text* at word boundaries onto lines of at most *width* chars.

    Never truncates and never adds an ellipsis. Hyphenated compounds are kept
    intact at word level; a single token longer than *width* is force-broken
    mid-character (the only case a word is split) so erroneous long labels can't
    run off the chart. Returns the text with embedded newlines.
    """
    text = (text or "").strip()
    if len(text) <= width:
        return text
    out: list[str] = []
    for ln in textwrap.wrap(
        text, width=width, break_long_words=False, break_on_hyphens=True
    ):
        out.extend(force_break_token(ln, width))
    return "\n".join(out) if out else text


def wrap_label_capped(text: str, width: int, max_lines: int) -> str:
    """Like wrap_label but caps the result to *max_lines* lines, truncating the
    last visible line with an ellipsis when the text doesn't fit.

    Ellipsis truncation is a deliberate last resort (user-approved): when a label
    has too many categories / too-long text to fit its row band, an ellipsis is
    preferred over labels overlapping each other. Full text is preserved whenever
    it fits in *max_lines*."""
    max_lines = max(1, max_lines)
    full = wrap_label(text, width)
    lines = full.split("\n")
    if len(lines) <= max_lines:
        return full
    kept = lines[:max_lines]
    last = kept[-1]
    if len(last) >= width:                 # make room for the ellipsis
        last = last[: max(1, width - 1)]
    kept[-1] = last.rstrip() + "…"
    return "\n".join(kept)


def render_empty_chart(ctx, message: str = "Ei tietoja näytettäväksi") -> None:
    """Render a centred 'no data' placeholder as a picture, so a chart with no
    categories (e.g. a scale variable with no value labels) degrades cleanly
    instead of crashing the deck. Counts as the chart's one picture."""
    fig, ax = new_figure(ctx)
    ax.axis("off")
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=13, color=MUTED, transform=ax.transAxes)
    place_picture(ctx, render_png(fig))


def series_is_empty(series) -> bool:
    """True when a series has nothing to plot (no categories, or every value is
    None/zero across all segments)."""
    cats = getattr(series, "categories", ())
    if not cats:
        return True
    stat = getattr(series, "statistic", "pct")
    for cat in cats:
        for seg in series.segments:
            cell = series.cells.get((cat, seg))
            if cell is not None and cell.value(stat) not in (None, 0, 0.0):
                return False
    return True


def new_figure(ctx):
    """Create a matplotlib Figure/Axes sized to ctx.slot, with nSight house style applied.

    Applies cream background and Liberation Sans font (REQ-C-25/27a).
    Minimum size enforced to maintain legibility at any slot dimension.
    """
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    fig = _new_agg_figure(w_in, h_in)
    ax = fig.subplots()
    fig.patch.set_facecolor(CREAM)
    ax.set_facecolor(CREAM)
    return fig, ax


def new_tall_figure(ctx, h_in: float):
    """Like new_figure but with a caller-chosen height (>= the slot height).

    Horizontal-bar charts grow taller as categories increase so every row keeps
    room for a ~2-line wrapped label at a legible font (instead of shrinking the
    font / truncating). The taller PNG is letterbox-placed top-aligned, filling
    the slot's height and using the otherwise-empty space below the chart."""
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(h_in, ctx.slot.height / _EMU_PER_IN)
    fig = _new_agg_figure(w_in, h_in)
    ax = fig.subplots()
    fig.patch.set_facecolor(CREAM)
    ax.set_facecolor(CREAM)
    return fig, ax


def render_png(fig) -> str:
    """Save figure to a temp PNG file at high quality and free it. Returns the path.

    The figure is an OO Agg Figure (not pyplot-managed), so there is no global
    registry entry to close — clearing it just releases its artists/memory."""
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    fig.savefig(path, dpi=200, bbox_inches="tight", pad_inches=0.04)
    fig.clear()
    return path


def place_picture(ctx, png_path: str) -> None:
    """Place png_path onto ctx.slide, scaled to FIT the slot preserving aspect.

    No chart element may ever be stretched or squeezed: the PNG is scaled by the
    limiting slot dimension (letterbox), so the rendered chart keeps its true
    aspect ratio.  Top-aligned so bar/line/funnel charts hug the question text
    above them rather than floating mid-slot with a large gap."""
    place_picture_square(ctx, png_path, valign="top")


# A classifier segment (or cross-tab combo) whose base is below this is too small
# to chart — its percentages would be noise (a "won't say" group of 1 → 100%). The
# engine still computes it exactly; we just don't PLOT it. Tunable.
MIN_SEGMENT_BASE = 10


def series_values(series):
    """Decompose a SeriesResult into (cats, segs, data) for chart rendering.

    Segments computed on a near-empty base are dropped (see MIN_SEGMENT_BASE) so a
    tiny classifier group never renders a misleading 100%. "Total" and single-series
    ("Total"-only) charts are always kept.

    Returns:
        cats: list of category labels (x-axis / bar groups)
        segs: list of segment labels (series)
        data: dict of seg -> list[float] (one value per category)
    """
    cats = list(series.categories)
    segs = [
        s for s in series.segments
        if s == "Total" or series.base_n.get(s, 0) >= MIN_SEGMENT_BASE
    ]
    if not segs:  # everything was tiny — fall back to the overall column
        segs = [s for s in series.segments if s == "Total"] or list(series.segments)
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
    fig = _new_agg_figure(sq, sq)
    ax = fig.subplots()
    fig.patch.set_facecolor(CREAM)
    ax.set_facecolor(CREAM)
    return fig, ax


def place_picture_square(ctx, png_path: str, valign: str = "center") -> None:
    """Place a PNG in ctx.slot preserving the PNG's true aspect ratio (letterbox).

    Reads the PNG's real pixel dimensions and scales it to fit *inside* the slot
    (scale to the limiting dimension).  This keeps a circular pie/radar chart
    circular — even when ``bbox_inches="tight"`` trimmed the saved PNG
    asymmetrically — instead of squishing a non-square PNG into an oval.

    Horizontally always centred.  Vertically: ``valign='center'`` (default, for
    symmetric charts like pie/radar) or ``valign='top'`` (for bar/line/funnel
    charts, so the chart hugs the question text above it instead of floating in
    the middle of the slot with a big gap).
    """
    from PIL import Image

    with Image.open(png_path) as im:
        px_w, px_h = im.size

    slot_w = ctx.slot.width
    slot_h = ctx.slot.height
    # Scale to fit within the slot, preserving aspect ratio (never upscale-distort).
    scale = min(slot_w / px_w, slot_h / px_h)
    disp_w = int(round(px_w * scale))
    disp_h = int(round(px_h * scale))
    left = ctx.slot.left + (slot_w - disp_w) // 2
    if valign == "top":
        top = ctx.slot.top
    else:
        top = ctx.slot.top + (slot_h - disp_h) // 2
    ctx.slide.shapes.add_picture(png_path, left, top, disp_w, disp_h)


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
