"""Image-mode bar/column chart builders — nSight house style (REQ-C-24/25/27a).

Builders: build_image_column, build_image_bar,
          build_image_column_stacked, build_image_bar_stacked.

Each renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.

House style applied:
- Cream figure/axes background, Liberation Sans font, INK tick labels
- Single series → TEAL; multi series → teal ramp (lightest → darkest)
- No top/right spines; GRIDC grid lines only; clean tick marks
- Data labels at bar ends (always shown, INK, bold)
- Auto-orientation: build_image_column switches to horizontal bars when there
  are > 6 categories or any label exceeds 14 characters to avoid x-label
  overlap. Explicit horizontal_bar / vertical_bar requests are always honoured.
- Long-label handling (R4.1): horizontal-bar y-axis labels are wrapped to at
  most 2 lines of ~22 chars; vertical-bar x-axis labels are truncated at 42
  chars.  Both use '…' to indicate clipped text.
- "Not answered" coloring (R4.2): bars whose category matches NOT_ANSWERED_LABEL
  are rendered in MUTED grey so non-response reads as distinct from real data.
"""
from __future__ import annotations

import textwrap

import numpy as np
from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values, format_value, style_legend,
)
from reportbuilder.render.house_style import (
    series_colors, INK, MUTED, GRIDC,
)
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL

# ---------------------------------------------------------------------------
# Label-length constants (R4.1)
# ---------------------------------------------------------------------------
_LABEL_WRAP_WIDTH: int = 22   # max chars per line for horizontal-bar y-axis labels
_LABEL_MAX_CHARS: int = 42    # truncation threshold for vertical-bar x-axis labels


# ---------------------------------------------------------------------------
# Label helpers (R4.1 — long-label fix)
# ---------------------------------------------------------------------------

def _wrap_label(text: str) -> str:
    """Wrap a y-axis label for horizontal bars to at most 2 lines of _LABEL_WRAP_WIDTH chars.

    Labels that already fit on one line (≤ _LABEL_WRAP_WIDTH chars) are returned
    unchanged.  Longer text is broken at word boundaries; text that still cannot
    fit in 2 lines is terminated with '…' on the second line.
    """
    if len(text) <= _LABEL_WRAP_WIDTH:
        return text
    return textwrap.fill(text, width=_LABEL_WRAP_WIDTH, max_lines=2, placeholder="…")


def _truncate_label(text: str, max_chars: int = _LABEL_MAX_CHARS) -> str:
    """Truncate an x-axis label for vertical bars to *max_chars*, appending '…' if clipped."""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1] + "…"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _apply_bar_style(ax, max_val: float = 100.0) -> None:
    """Apply house-style spines, grid, and tick formatting to a bar axes."""
    # Remove all spines, then restore left spine only (horizontal bars)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color("#C9C1B4")
    ax.spines["left"].set_linewidth(1.0)

    # Vertical reference lines at every 20-unit interval
    ax_max = min(100.0, max(max_val * 1.15, 10.0))
    for xv in [20, 40, 60, 80, 100]:
        if xv <= ax_max:
            ax.axvline(xv, color=GRIDC, lw=0.8, zorder=1)

    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0)

    x_ticks = [v for v in [0, 20, 40, 60, 80, 100] if v <= ax_max]
    ax.set_xticks(x_ticks)
    ax.set_xticklabels([str(v) for v in x_ticks], fontsize=9.5, color=MUTED)
    ax.set_xlim(0, ax_max)


def _apply_column_style(ax, max_val: float = 100.0) -> None:
    """Apply house-style spines, grid, and tick formatting to a column axes."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)

    ax_max = min(100.0, max(max_val * 1.15, 10.0))
    for yv in [20, 40, 60, 80, 100]:
        if yv <= ax_max:
            ax.axhline(yv, color=GRIDC, lw=0.8, zorder=1)

    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0)

    y_ticks = [v for v in [0, 20, 40, 60, 80, 100] if v <= ax_max]
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([str(v) for v in y_ticks], fontsize=9.5, color=MUTED)
    ax.set_ylim(0, ax_max)


def _label_offset(max_val: float) -> float:
    """Small positive offset for data labels (proportional to axis range)."""
    return max(0.5, max_val * 0.01)


def _should_orient_horizontal(cats: list[str]) -> bool:
    """Return True if auto-orientation picks horizontal bars.

    Horizontal is preferred when there are many categories (> 6) or any
    category label is long (> 14 characters), to avoid x-axis label overlap.
    """
    return len(cats) > 6 or any(len(c) > 14 for c in cats)


# ---------------------------------------------------------------------------
# build_image_column  (vertical bars; may auto-switch to horizontal)
# ---------------------------------------------------------------------------

def build_image_column(ctx) -> None:
    """Vertical grouped bar chart with house style; auto-orients to horizontal
    when many categories or long labels are detected (REQ-C-24b/f, REQ-C-27a)."""
    cats, segs, data = series_values(ctx.series)

    # Auto-orientation: switch to horizontal if labels would crowd the x-axis
    if _should_orient_horizontal(cats):
        _render_bar_h(ctx, cats, segs, data)
        return

    _render_column_v(ctx, cats, segs, data)


def _render_column_v(ctx, cats, segs, data) -> None:
    """Internal vertical-bar renderer."""
    fig, ax = new_figure(ctx)
    clrs = series_colors(len(segs))

    n_cats = len(cats)
    n_segs = len(segs)
    x = np.arange(n_cats)
    width = 0.7 / n_segs if n_segs > 1 else 0.5

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=0.0)

    for i, seg in enumerate(segs):
        vals = data[seg]
        offset = (i - n_segs / 2 + 0.5) * width if n_segs > 1 else 0.0
        # R4.2: "Not answered" bar gets MUTED grey; all others get the series colour.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in cats]
        bars = ax.bar(
            x + offset, vals, width=width,
            label=seg, color=bar_clrs, edgecolor="none", zorder=3,
        )
        off = _label_offset(max_val)
        for bar, v in zip(bars, vals):
            if v is not None:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + off,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    ha="center", va="bottom",
                    fontsize=9.5, fontweight="bold", color=INK, zorder=5,
                )

    # R4.1: truncate long x-axis labels so they don't crowd the plot.
    display_cats = [_truncate_label(c) for c in cats]
    ax.set_xticks(x)
    ax.set_xticklabels(display_cats, fontsize=11.5, color=INK)
    _apply_column_style(ax, max_val)

    if ctx.spec.elements.legend and n_segs > 1:
        _style_legend(ax)

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# build_image_bar  (horizontal bars — always horizontal)
# ---------------------------------------------------------------------------

def build_image_bar(ctx) -> None:
    """Horizontal grouped bar chart with house style (REQ-C-24b/f, REQ-C-27a)."""
    cats, segs, data = series_values(ctx.series)
    _render_bar_h(ctx, cats, segs, data)


def _render_bar_h(ctx, cats, segs, data) -> None:
    """Internal horizontal-bar renderer shared by bar + auto-orient column."""
    fig, ax = new_figure(ctx)
    clrs = series_colors(len(segs))

    n_cats = len(cats)
    n_segs = len(segs)
    y = np.arange(n_cats)[::-1]   # top category at top of plot
    height = 0.7 / n_segs if n_segs > 1 else 0.62

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=0.0)

    for i, seg in enumerate(segs):
        vals = data[seg]
        offset = (i - n_segs / 2 + 0.5) * height if n_segs > 1 else 0.0
        ys = y + offset
        # R4.2: "Not answered" bar gets MUTED grey; all others get the series colour.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in cats]
        ax.barh(
            ys, vals, height=height,
            label=seg, color=bar_clrs, edgecolor="none", zorder=3,
        )
        off = _label_offset(max_val)
        for yi, v in zip(ys, vals):
            if v is not None:
                ax.text(
                    v + off, yi,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    va="center", ha="left",
                    fontsize=9.5, fontweight="bold", color=INK, zorder=5,
                )

    # R4.1: wrap long y-axis labels to ≤ 2 lines so bars always have room.
    display_cats = [_wrap_label(c) for c in cats]
    ax.set_yticks(y)
    ax.set_yticklabels(display_cats, fontsize=11.5, color=INK)
    ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
    _apply_bar_style(ax, max_val)

    if ctx.spec.elements.legend and n_segs > 1:
        _style_legend(ax, loc="lower right")

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# build_image_column_stacked
# ---------------------------------------------------------------------------

def build_image_column_stacked(ctx) -> None:
    """Stacked vertical bar chart with house style."""
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    clrs = series_colors(len(segs))

    x = np.arange(len(cats))
    bottoms = np.zeros(len(cats))
    all_vals = [sum(data[s][i] or 0 for s in segs) for i in range(len(cats))]
    max_val = max(all_vals, default=0.0)
    flat_vals = [v for seg in segs for v in data[seg] if v is not None]

    for i, seg in enumerate(segs):
        vals = np.array([v or 0.0 for v in data[seg]])
        # R4.2: "Not answered" category bars get MUTED grey.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in cats]
        bars = ax.bar(x, vals, bottom=bottoms, label=seg, color=bar_clrs,
                      edgecolor="none", zorder=3)
        for bar, v, b in zip(bars, vals, bottoms):
            mid = b + v / 2
            if v > 1:   # skip label if segment is too thin
                ax.text(
                    bar.get_x() + bar.get_width() / 2, mid,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, flat_vals),
                    ha="center", va="center",
                    fontsize=9.0, fontweight="bold", color=INK, zorder=5,
                )
        bottoms = bottoms + vals

    # R4.1: truncate long x-axis labels.
    display_cats = [_truncate_label(c) for c in cats]
    ax.set_xticks(x)
    ax.set_xticklabels(display_cats, fontsize=11.5, color=INK)
    _apply_column_style(ax, max_val)

    if ctx.spec.elements.legend and len(segs) > 1:
        _style_legend(ax)

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# build_image_bar_stacked
# ---------------------------------------------------------------------------

def build_image_bar_stacked(ctx) -> None:
    """Stacked horizontal bar chart with house style."""
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    clrs = series_colors(len(segs))

    n_cats = len(cats)
    y = np.arange(n_cats)[::-1]
    lefts = np.zeros(n_cats)
    all_totals = [sum(data[s][i] or 0 for s in segs) for i in range(n_cats)]
    max_val = max(all_totals, default=0.0)
    flat_vals = [v for seg in segs for v in data[seg] if v is not None]

    for i, seg in enumerate(segs):
        vals = np.array([v or 0.0 for v in data[seg]])
        # R4.2: "Not answered" category bars get MUTED grey.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in cats]
        ax.barh(y, vals, left=lefts, label=seg, color=bar_clrs,
                edgecolor="none", zorder=3)
        for yi, v, l in zip(y, vals, lefts):
            mid = l + v / 2
            if v > 1:
                ax.text(
                    mid, yi,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, flat_vals),
                    ha="center", va="center",
                    fontsize=9.0, fontweight="bold", color=INK, zorder=5,
                )
        lefts = lefts + vals

    # R4.1: wrap long y-axis labels.
    display_cats = [_wrap_label(c) for c in cats]
    ax.set_yticks(y)
    ax.set_yticklabels(display_cats, fontsize=11.5, color=INK)
    ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
    _apply_bar_style(ax, max_val)

    if ctx.spec.elements.legend and len(segs) > 1:
        _style_legend(ax, loc="lower right")

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# Shared legend styler (thin wrapper around the shared helper in _mpl)
# ---------------------------------------------------------------------------

def _style_legend(ax, loc: str = "best") -> None:
    """Apply house-style formatting to an axes legend."""
    style_legend(ax, loc)
