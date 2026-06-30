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
- Long-label handling: labels are NEVER ellipsis-cut and NEVER allowed to
  overlap.  Horizontal-bar y-axis labels are wrapped at word boundaries onto as
  many lines as needed (full text).  Vertical-bar x-axis labels are wrapped AND
  rotated 30° (ha="right") so neighbouring labels never collide.
- "Not answered" coloring (R4.2): bars whose category matches NOT_ANSWERED_LABEL
  are rendered in MUTED grey so non-response reads as distinct from real data.
"""
from __future__ import annotations

import math
import textwrap

import numpy as np
from reportbuilder.render.image._mpl import (
    new_figure, new_tall_figure, render_png, place_picture, place_picture_square,
    series_values, format_value, style_legend, force_break_token, wrap_label,
    wrap_label_capped,
)
from reportbuilder.render.house_style import (
    series_colors, scale_colors, INK, MUTED, GRIDC,
)
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL

# ---------------------------------------------------------------------------
# Label-wrap constants — labels are wrapped, never truncated/ellipsis-cut.
# ---------------------------------------------------------------------------
_LABEL_WRAP_WIDTH: int = 30   # chars per line for horizontal-bar y-axis labels (wider gutter)
_HBAR_LABEL_WRAP_WIDTH: int = 42  # wider wrap for hbar y-labels → fewer lines, taller font
_HBAR_ROW_IN: float = 0.52        # vertical inches reserved per category row (fits 2 label lines)
_XLABEL_WRAP_WIDTH: int = 20  # chars per line for (rotated) vertical-bar x-axis labels
_XTICK_ROTATION: int = 30     # rotation (deg) for vertical-bar x-axis tick labels


def _hbar_row_pt(n_cats: int, fig_h_in: float) -> float:
    """Vertical space (in points) available to ONE category row."""
    usable_pt = fig_h_in * 72.0 * 0.80   # ~80% of figure height is the plot area
    return usable_pt / max(n_cats, 1)


def _hbar_label_fontsize(n_cats: int, fig_h_in: float) -> float:
    """Pick a y-axis label font size that fits *n_cats* rows in the chart's
    vertical space, aiming for up to ~2 wrapped lines per row.

    The slide slot height is a hard cap, so with many long-label categories the
    font must shrink to the per-row band to avoid overlap. Clamped to a legible
    range and always below the slide title size."""
    row_pt = _hbar_row_pt(n_cats, fig_h_in)
    fs = row_pt / (2.0 * 1.25)   # target 2 lines; 1.25 = line-height factor
    return max(7.0, min(11.0, fs))


# ---------------------------------------------------------------------------
# Label helpers — wrap to full text, NEVER ellipsis-cut (no '…' anywhere).
# ---------------------------------------------------------------------------

def _wrap_label(text: str, width: int = _LABEL_WRAP_WIDTH) -> str:
    """Wrap a category label at word boundaries onto balanced lines.

    Smarter line layout: wraps at word boundaries, keeps hyphenated compounds
    (e.g. "Mainio-kodit") intact, and BALANCES the lines — once the number of
    lines is fixed it uses the narrowest width that still fits in that many
    lines, so we don't get one full line plus a lonely orphan word. The full
    text is always preserved (never truncated, never an ellipsis); a single
    token longer than *width* is broken only as a last resort.
    """
    if len(text) <= width:
        return text

    def _wrap(w: int) -> list[str]:
        # Wrap at spaces and existing hyphens only — never split a word
        # mid-character (break_long_words=False). A token longer than the width
        # stays whole (the gutter widens to fit it) rather than "pä\nihde…".
        return textwrap.wrap(
            text, width=w, break_long_words=False, break_on_hyphens=True
        )

    n_lines = len(_wrap(width))
    # Find the narrowest width that still fits in n_lines → balanced line lengths.
    target = width
    for w in range(math.ceil(len(text) / max(n_lines, 1)), width + 1):
        if len(_wrap(w)) <= n_lines:
            target = w
            break
    # Last resort: a single token still wider than the gutter (a pathological
    # unbroken long word) is force-broken so it can't run off the chart.
    out: list[str] = []
    for ln in _wrap(target):
        out.extend(force_break_token(ln, width))
    return "\n".join(out)


def _wrap_xtick_label(text: str) -> str:
    """Wrap a vertical-bar x-axis label (narrower wrap; rotation handles the rest)."""
    return _wrap_label(text, width=_XLABEL_WRAP_WIDTH)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _value_axis(max_val: float, statistic: str) -> tuple[float, list[float]]:
    """Return (axis_max, gridline/tick positions) for the VALUE axis.

    Percentages use the fixed 0..100 scale (capped, 20-step gridlines). Counts
    and means have no 100 cap — the axis scales to the data with ~5 "nice" ticks,
    otherwise a count of e.g. 600 would overflow a 0..100 axis and its data
    labels (placed at x=value) would blow up the tight bounding box, shrinking
    the whole chart to a stamp."""
    if statistic == "pct":
        ax_max = min(100.0, max(max_val * 1.15, 10.0))
        return ax_max, [v for v in [0, 20, 40, 60, 80, 100] if v <= ax_max]
    # count / mean: nice round ticks covering the data range.
    vmax = max(max_val * 1.12, 1.0)
    raw = vmax / 5.0
    mag = 10.0 ** math.floor(math.log10(raw)) if raw > 0 else 1.0
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    top = math.ceil(vmax / step) * step
    n = int(round(top / step))
    ticks = [round(i * step, 6) for i in range(n + 1)]
    return top, ticks


def _tick_text(v: float) -> str:
    """Integer-looking tick → no decimals; otherwise trim trailing zeros."""
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


def _legend_below(ax, n_segs: int) -> None:
    """Place a stacked chart's scale legend in a single horizontal row BELOW the
    plot (a stacked bar fills the whole plot width, so an in-axes legend would
    cover the bars). bbox_inches='tight' expands the figure to include it."""
    leg = ax.legend(
        loc="upper center", bbox_to_anchor=(0.5, -0.08),
        ncol=min(n_segs, 5), frameon=False, fontsize=9.5,
        handlelength=1.1, columnspacing=1.4, handletextpad=0.5,
    )
    if leg is not None:
        for t in leg.get_texts():
            t.set_color(INK)


def _apply_bar_style(ax, max_val: float = 100.0, statistic: str = "pct") -> None:
    """Apply house-style spines, grid, and tick formatting to a bar axes."""
    # Remove all spines, then restore left spine only (horizontal bars)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color("#C9C1B4")
    ax.spines["left"].set_linewidth(1.0)

    ax_max, ticks = _value_axis(max_val, statistic)
    for xv in ticks:
        if xv > 0:
            ax.axvline(xv, color=GRIDC, lw=0.8, zorder=1)

    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0)

    ax.set_xticks(ticks)
    ax.set_xticklabels([_tick_text(v) for v in ticks], fontsize=9.5, color=MUTED)
    ax.set_xlim(0, ax_max)


def _apply_column_style(ax, max_val: float = 100.0, statistic: str = "pct") -> None:
    """Apply house-style spines, grid, and tick formatting to a column axes."""
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)

    ax_max, y_ticks = _value_axis(max_val, statistic)
    for yv in y_ticks:
        if yv > 0:
            ax.axhline(yv, color=GRIDC, lw=0.8, zorder=1)

    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0)

    ax.set_yticks(y_ticks)
    ax.set_yticklabels([_tick_text(v) for v in y_ticks], fontsize=9.5, color=MUTED)
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
    """Vertical grouped (column) bar chart with house style.

    Always renders vertical — `vertical_bar` and `horizontal_bar` are now
    distinct chart types, so an explicit vertical choice is honoured rather than
    silently auto-flipped to horizontal. (The suitability scorer already ranks
    vertical low for many/long labels, so it is never auto-CHOSEN for those.)
    (REQ-C-24b/f, REQ-C-27a)"""
    cats, segs, data = series_values(ctx.series)
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

    # Wrap + rotate x-axis labels so they are shown in full and never overlap.
    display_cats = [_wrap_xtick_label(c) for c in cats]
    ax.set_xticks(x)
    ax.set_xticklabels(
        display_cats, fontsize=10.5, color=INK,
        rotation=_XTICK_ROTATION, ha="right", rotation_mode="anchor",
    )
    _apply_column_style(ax, max_val, ctx.series.statistic)

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
    n_cats = len(cats)
    # Reserve as many label lines as the LONGEST label actually needs (2..3), so
    # normal long labels wrap in full and are never truncated. Only a pathological
    # label still longer than 3 lines at the wide wrap width is ellipsised.
    wrapped_full = [wrap_label(c, _HBAR_LABEL_WRAP_WIDTH) for c in cats]
    label_lines = min(3, max(2, max((w.count("\n") + 1 for w in wrapped_full), default=1)))
    # Grow the figure taller as categories (and reserved label lines) increase so
    # every row has room — preferring more space (a bigger chart that fills the
    # slide) over shrinking the font or truncating.
    row_in = label_lines * 0.18 + 0.16
    fig, ax = new_tall_figure(ctx, n_cats * row_in + 1.2)
    clrs = series_colors(len(segs))

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
    # The figure is sized so each row fits `label_lines` wrapped lines; size the
    # font to that band (kept below the title size). Ellipsis is a true last
    # resort — only a label STILL longer than `label_lines` (≤3) is truncated.
    fig_h_in = float(fig.get_size_inches()[1])
    row_pt = _hbar_row_pt(n_cats, fig_h_in)
    max_lines = label_lines
    ylabel_fs = max(8.5, min(11.5, row_pt / (max_lines * 1.3)))
    value_fs = max(8.0, min(9.5, ylabel_fs))

    off = _label_offset(max_val)
    for i, seg in enumerate(segs):
        vals = data[seg]
        offset = (i - n_segs / 2 + 0.5) * height if n_segs > 1 else 0.0
        ys = y + offset
        for yi, v in zip(ys, vals):
            if v is not None:
                ax.text(
                    v + off, yi,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    va="center", ha="left",
                    fontsize=value_fs, fontweight="bold", color=INK, zorder=5,
                )

    # Wrap y-axis labels; cap to the lines that fit the band (ellipsis last resort).
    display_cats = [
        wrap_label_capped(c, _HBAR_LABEL_WRAP_WIDTH, max_lines) for c in cats
    ]
    ax.set_yticks(y)
    ax.set_yticklabels(display_cats, fontsize=ylabel_fs, color=INK)
    ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
    _apply_bar_style(ax, max_val, ctx.series.statistic)

    if ctx.spec.elements.legend and n_segs > 1:
        _style_legend(ax, loc="lower right")

    png = render_png(fig)
    # Aspect-preserving placement, top-aligned so the chart hugs the question
    # text above it (never stretch/squeeze into the slot).
    place_picture_square(ctx, png, valign="top")


# ---------------------------------------------------------------------------
# build_image_column_stacked
# ---------------------------------------------------------------------------

def _stacked_layout(series):
    """Decompose a segmented series into a clean 100%-stacked layout.

    A stacked bar compares composition: each BAR is a classifying-variable
    segment and the STACK is the question's answer categories. The engine's
    per-segment percentages sum to 100 within a segment (column %), so each bar
    fills exactly 100% — no overshoot, no floating 'Total'. Returns
    (bars, stack, data) where data[stack_member] = [value per bar].

    With no classifier (segments == ('Total',)) there is nothing to compose, so
    the answer categories become the bars with a single stack member.
    """
    cats, segs, data = series_values(series)
    bars = [s for s in segs if s != "Total"]
    if len(bars) <= 1:
        # No real classifier split — fall back to one bar per category.
        return cats, ["Total"], {"Total": data.get("Total", [0.0] * len(cats))}
    stack = cats
    new_data = {
        qcat: [data[seg][ci] for seg in bars] for ci, qcat in enumerate(cats)
    }
    return bars, stack, new_data


def build_image_column_stacked(ctx) -> None:
    """Stacked vertical (100%) bar chart: bars = classifier segments, stack =
    answer categories (house style)."""
    cats, segs, data = _stacked_layout(ctx.series)
    fig, ax = new_figure(ctx)
    # Stack segments are ordered scale levels → monotonic light→dark gradient.
    clrs = scale_colors(len(segs))

    x = np.arange(len(cats))
    flat_vals = [v for seg in segs for v in data[seg] if v is not None]

    # 100%-stacked: every column must reach exactly 100. Normalise each column's
    # segment HEIGHTS to its own total (rounded percentages sum to 99–101) so the
    # tops align, while the data LABELS still show the original percentages.
    totals = np.array([sum(data[s][i] or 0.0 for s in segs) for i in range(len(cats))])
    norm = np.where(totals > 0, 100.0 / totals, 1.0)
    bottoms = np.zeros(len(cats))

    for i, seg in enumerate(segs):
        orig = np.array([data[seg][j] or 0.0 for j in range(len(cats))])
        heights = orig * norm
        # R4.2: "Not answered" category bars get MUTED grey.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in cats]
        bars = ax.bar(x, heights, bottom=bottoms, label=seg, color=bar_clrs,
                      edgecolor="none", zorder=3)
        for bar, ov, b, h in zip(bars, orig, bottoms, heights):
            if h > 1:   # skip label if segment is too thin
                ax.text(
                    bar.get_x() + bar.get_width() / 2, b + h / 2,
                    format_value(ov, ctx.series.statistic, ctx.spec.number_format, flat_vals),
                    ha="center", va="center",
                    fontsize=9.0, fontweight="bold", color=INK, zorder=5,
                )
        bottoms = bottoms + heights

    # Wrap + rotate x-axis labels so they are shown in full and never overlap.
    display_cats = [_wrap_xtick_label(c) for c in cats]
    ax.set_xticks(x)
    ax.set_xticklabels(
        display_cats, fontsize=10.5, color=INK,
        rotation=_XTICK_ROTATION, ha="right", rotation_mode="anchor",
    )
    _apply_column_style(ax, 100.0)   # 100%-stacked → fixed 0–100 axis

    if ctx.spec.elements.legend and len(segs) > 1:
        _legend_below(ax, len(segs))

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# build_image_bar_stacked
# ---------------------------------------------------------------------------

def build_image_bar_stacked(ctx) -> None:
    """Stacked horizontal (100%) bar chart: bars = classifier segments, stack =
    answer categories (house style)."""
    cats, segs, data = _stacked_layout(ctx.series)
    fig, ax = new_figure(ctx)
    # Stack segments are ordered scale levels → monotonic light→dark gradient.
    clrs = scale_colors(len(segs))

    n_cats = len(cats)
    y = np.arange(n_cats)[::-1]
    flat_vals = [v for seg in segs for v in data[seg] if v is not None]

    # 100%-stacked: every bar must fill exactly to 100. Rounded category
    # percentages sum to 99–101 per bar, so normalise each bar's segment WIDTHS to
    # its own total — the right edges then align perfectly — while the data LABELS
    # still show the original (rounded) percentages.
    totals = np.array([sum(data[s][i] or 0.0 for s in segs) for i in range(n_cats)])
    norm = np.where(totals > 0, 100.0 / totals, 1.0)
    lefts = np.zeros(n_cats)

    for i, seg in enumerate(segs):
        orig = np.array([data[seg][j] or 0.0 for j in range(n_cats)])
        widths = orig * norm
        # R4.2: "Not answered" category bars get MUTED grey.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in cats]
        ax.barh(y, widths, left=lefts, label=seg, color=bar_clrs,
                edgecolor="none", zorder=3)
        for yi, ov, l, w in zip(y, orig, lefts, widths):
            if w > 1:
                ax.text(
                    l + w / 2, yi,
                    format_value(ov, ctx.series.statistic, ctx.spec.number_format, flat_vals),
                    ha="center", va="center",
                    fontsize=9.0, fontweight="bold", color=INK, zorder=5,
                )
        lefts = lefts + widths

    # Wrap long y-axis labels onto as many lines as needed (full text, no '…').
    display_cats = [_wrap_label(c) for c in cats]
    ax.set_yticks(y)
    ax.set_yticklabels(display_cats, fontsize=11.5, color=INK)
    ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
    _apply_bar_style(ax, 100.0)   # 100%-stacked → fixed 0–100 axis

    if ctx.spec.elements.legend and len(segs) > 1:
        _legend_below(ax, len(segs))

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# Shared legend styler (thin wrapper around the shared helper in _mpl)
# ---------------------------------------------------------------------------

def _style_legend(ax, loc: str = "best") -> None:
    """Apply house-style formatting to an axes legend."""
    style_legend(ax, loc)
