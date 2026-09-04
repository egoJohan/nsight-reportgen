"""Image-mode bar/column chart builders — nSight house style (REQ-C-24/25/27a).

Builders: build_image_column, build_image_bar,
          build_image_column_stacked, build_image_bar_stacked.

Each renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.

House style applied:
- Slide-background figure/axes background, Liberation Sans font, ink-tone tick labels
- Single series → TEAL; multi series → teal ramp (lightest → darkest)
- No top/right spines; grid-tone grid lines only; clean tick marks
- Data labels at bar ends (always shown, ink-tone, bold)

Furniture (ink/muted/grid text and gridline colours) is derived from the
slide's own background via `chart_furniture` (house_style.furniture_colors) —
INK/MUTED/GRIDC unchanged on a light slide (byte-identical to before this
existed), flipped for legibility on a dark one.
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
import re
import textwrap

import numpy as np
from reportbuilder.render.image._mpl import (apply_axis_titles, chart_accent,
    chart_furniture, new_figure, new_tall_figure, new_figure_grid, render_png, place_picture,
    place_picture_square, series_values, format_value, label_floor, default_label_floor, style_legend,
    force_break_token, wrap_label, wrap_label_capped,
    _new_agg_figure, _EMU_PER_IN,
)
from reportbuilder.render.house_style import (
    series_colors, scale_colors, contrast_ink, MUTED, register_fonts,
)
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL
from reportbuilder.stats.series import PARTITION_UNDERSHOOT_TOL_PCT
from reportbuilder.model.report import default_label
from reportbuilder.render.image._mpl import template_palette


def _format_summary(val: float, fn: str, nf) -> str:
    """Format one row-summary value: mean → decimal (3.8); net → signed points
    (+51); sums/top → percent (65 %)."""
    if fn == "mean":
        return f"{val:.{nf.mean_decimals}f}"
    if fn == "net":
        return f"{val:+.{nf.pct_decimals}f}"
    s = f"{val:.{nf.pct_decimals}f}"
    return f"{s} %" if nf.show_pct_sign else s


def _row_summary_by_bar(series, bars) -> list[float | None]:
    """The row-summary value for each of `bars`, or None where there is none.

    The engine keys its values by bar label because the renderer does NOT draw every
    segment the engine computes — a near-empty classifier group is dropped
    (MIN_SEGMENT_BASE) and "Total" can be hidden — so zipping the values against the
    surviving bars would silently shift each one onto its neighbour's row."""
    rs = series.row_summaries
    if not rs:
        return [None] * len(bars)
    keys = getattr(series, "row_summary_keys", ())
    if not keys:                                # legacy/hand-built series: positional
        return list(rs) + [None] * (len(bars) - len(rs))
    by_key = dict(zip(keys, rs))
    return [by_key.get(b) for b in bars]


def _draw_row_summary(ctx, ax, y, bars, axis_max: float = 100.0) -> None:
    """Right-hand per-row summary column (row_summary feature): a header above the
    top bar and one value per bar, aligned to `y`. No-op when the series carries no
    row_summaries. (spec 2026-07-07-row-summary-column)

    `axis_max` is the value the bars are drawn against — 100 for a 100%-stacked
    chart, the real maximum for one drawn at TRUE widths (see `_stack_scaling`).
    The strip is placed proportionally to it, so it stays just off the right end
    of the bars either way instead of landing inside a 0-465 plot."""
    if len(y) == 0:
        # No bars to summarise — `min(y)`/`max(y)` below would raise on an empty
        # sequence. Callers omit an empty panel, so this is belt-and-braces for any
        # future caller that does not. (final review I3)
        return
    vals = _row_summary_by_bar(ctx.series, bars)
    if all(v is None for v in vals):
        return
    ink, muted, _grid = chart_furniture(ctx)
    fn = ctx.spec.row_summary_fn
    nf = ctx.spec.number_format
    header = ctx.spec.row_summary_label or default_label(fn)
    # Written as `x * axis_max / 100` (not `x * factor`) so the 100%-stacked case
    # lands on EXACTLY the historical 118 / 109 — no float drift.
    ax.set_xlim(0, 118.0 * axis_max / 100.0)              # reserve ~15% strip on the right
    ax.set_ylim(min(y) - 0.7, max(y) + 1.2)               # room for the header row
    col_x = 109.0 * axis_max / 100.0
    ax.text(col_x, max(y) + 0.9, header, ha="center", va="center",
            fontsize=9.0, fontweight="bold", color=muted, zorder=6)
    for yi, val in zip(y, vals):
        if val is None:
            continue
        ax.text(col_x, yi, _format_summary(val, fn, nf), ha="center", va="center",
                fontsize=11.0, fontweight="bold", color=ink, zorder=6)

# ---------------------------------------------------------------------------
# Label-wrap constants — labels are wrapped, never truncated/ellipsis-cut.
# ---------------------------------------------------------------------------
_LABEL_WRAP_WIDTH: int = 30   # chars per line for horizontal-bar y-axis labels (wider gutter)
_HBAR_LABEL_WRAP_WIDTH: int = 42  # wider wrap for hbar y-labels → fewer lines, taller font
_HBAR_ROW_IN: float = 0.52        # vertical inches reserved per category row (fits 2 label lines)
_XLABEL_WRAP_WIDTH: int = 20  # chars per line for (rotated) vertical-bar x-axis labels
_XTICK_ROTATION: int = 30     # rotation (deg) for vertical-bar x-axis tick labels
# Beyond this many segments the per-bar value labels collide, so they are dropped
# (axis grid + legend carry the read). Vertical columns get narrow sooner than the
# horizontal layout, so its threshold is lower.
_MAX_LABELED_SEGMENTS_V: int = 4
# Horizontal clustered bars: label a bar only when it is at least this TALL (points).
# Density (categories × segments), not a raw segment count, decides collision — a single
# question split by a background group has tall bars that easily hold a label, whereas a
# dense two-classifier cross-tab makes thin ones. (Mean/median render clustered, so this
# is what makes their by-group value labels appear.)
_MIN_LABEL_BAR_PT: float = 5.0


#: The size the style carries when nobody has chosen one. A template that has
#: not been corrected leaves the auto-fit alone, which is what it is for.
_DEFAULT_LABEL_PT = 10


def _explicit_label_pt(ctx) -> float:
    """An author's own row-label size, or 0 to keep auto-fitting."""
    try:
        _family, size = ctx.style.font_for("category_names")
    except Exception:  # noqa: BLE001
        return 0.0
    return float(size) if size and int(size) != _DEFAULT_LABEL_PT else 0.0


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
    the whole chart to a stamp.

    A percentage above 100 is not a rounding artefact to be clipped: it is a
    stacked chart whose segments genuinely overlap (a multi-response question,
    shares summing to e.g. 465%) drawn at its TRUE widths (`_stack_scaling`).
    Capping that at 100 would push most of every bar off the axis — precisely
    the dishonesty this axis exists to avoid — so it falls through to the
    nice-tick branch and the axis reads to the real maximum."""
    if statistic == "pct" and max_val <= 100.0:
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


# Up to this many series, a below-the-plot legend is compact enough; beyond it a
# right-side vertical legend keeps the plot large (uses the spare horizontal space).
_LEGEND_BELOW_MAX: int = 5


def _place_series_legend(fig, ax, segs, ctx, *, vertical: bool) -> None:
    """Dynamic legend placement to keep the plot as large as possible.

    Few series → a compact row BELOW the plot. Many series (e.g. a cross-tab of two
    classifiers, which yields long combo labels) → a single-column legend to the
    RIGHT, with the axes shrunk to make room *within* the figure so the plot keeps
    its height instead of being squeezed by a wide multi-row legend below."""
    n = len(segs)
    if n <= _LEGEND_BELOW_MAX:
        _legend_below(ax, n, ctx, y=-0.22 if vertical else -0.08)
        return
    # Right-side vertical legend. Labels are WRAPPED + ellipsised to a bounded width
    # so long combo labels (e.g. gender × a long life-situation label) can't balloon
    # the legend column and shrink the plot. The axes shrink to make room within the
    # figure; the font steps down as the series count grows so a long list still fits.
    handles, labels = ax.get_legend_handles_labels()
    wrapped = [_wrap_legend_label(lbl) for lbl in labels]
    box = ax.get_position()
    ax.set_position([box.x0, box.y0, box.width * 0.72, box.height])
    fs = 9.0 if n <= 12 else (8.0 if n <= 20 else 7.0)
    leg = ax.legend(
        handles, wrapped,
        loc="center left", bbox_to_anchor=(1.02, 0.5),
        ncol=1, frameon=False, fontsize=fs,
        handlelength=1.0, handletextpad=0.5, labelspacing=0.4,
    )
    if leg is not None:
        ink, _muted, _grid = chart_furniture(ctx)
        for t in leg.get_texts():
            t.set_color(ink)


def _wrap_legend_label(label: str, width: int = 26, max_lines: int = 2) -> str:
    """Wrap a legend label to at most `max_lines` of ~`width` chars, ellipsising any
    overflow — bounds the legend column width so long combo labels don't dominate."""
    lines = textwrap.wrap(label, width=width) or [label]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: width - 1].rstrip() + "…"
    return "\n".join(lines)


def _rowmajor_legend(handles, labels, ncol):
    """Reorder legend entries so a matplotlib (column-major) legend READS left-to-
    right, top-to-bottom — i.e. in the SAME order as the bars/stack, not scrambled
    across columns. (Matplotlib fills columns first; this un-does that.)"""
    order = [k for i in range(ncol) for k in range(i, len(handles), ncol)]
    return [handles[k] for k in order], [labels[k] for k in order]


def _leading_number(label: str) -> int | None:
    """The integer a legend label starts with ('1 - Täysin eri mieltä' → 1, '2' → 2), or
    None when it doesn't begin with a number (a categorical group like 'Uusimaa')."""
    m = re.match(r"\s*(\d+)", str(label))
    return int(m.group(1)) if m else None


def _legend_below(ax, n_segs: int, ctx, y: float = -0.08) -> None:
    """Place a chart's legend in a horizontal row BELOW the plot (an in-axes legend
    would cover the bars). `y` is the bbox anchor offset — push it lower for charts
    with rotated x-axis tick labels (clustered vertical bars) so it clears them.
    bbox_inches='tight' expands the figure to include it."""
    handles, labels = ax.get_legend_handles_labels()
    # A numeric rating scale (every level starts with its point number, e.g. "1 - Täysin
    # eri mieltä", "2", … "7 - …") shows JUST the numbers in the legend — the endpoint
    # wording moves to the subtitle. Keeps the legend short and even (no ragged gaps from
    # long endpoint labels stacking under bare numbers).
    nums = [_leading_number(l) for l in labels]
    numeric_scale = len(nums) >= 3 and all(n is not None for n in nums)
    if numeric_scale:
        labels = [str(n) for n in nums]
    # ≤7 short items go on ONE row; larger sets wrap into ≤5 columns (row-major).
    one_row = n_segs <= 7 and (numeric_scale or n_segs <= 5)
    ncol = n_segs if one_row else min(n_segs, 5)
    if not one_row:
        handles, labels = _rowmajor_legend(handles, labels, ncol)
    leg = ax.legend(
        handles, labels,
        loc="upper center", bbox_to_anchor=(0.5, y),
        ncol=ncol, frameon=False, fontsize=9.5,
        handlelength=1.1, columnspacing=1.2, handletextpad=0.5,
    )
    if leg is not None:
        ink, _muted, _grid = chart_furniture(ctx)
        for t in leg.get_texts():
            t.set_color(ink)


def _apply_bar_style(ax, ctx, max_val: float = 100.0, statistic: str = "pct") -> None:
    """Apply house-style spines, grid, and tick formatting to a bar axes."""
    _ink, muted, grid = chart_furniture(ctx)
    # Remove all spines, then restore left spine only (horizontal bars)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["left"].set_visible(True)
    ax.spines["left"].set_color("#C9C1B4")
    ax.spines["left"].set_linewidth(1.0)

    ax_max, ticks = _value_axis(max_val, statistic)
    for xv in ticks:
        if xv > 0:
            ax.axvline(xv, color=grid, lw=0.8, zorder=1)

    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0)

    ax.set_xticks(ticks)
    ax.set_xticklabels([_tick_text(v) for v in ticks], fontsize=9.5, color=muted)
    ax.set_xlim(0, ax_max)
    apply_axis_titles(ax, ctx.spec, _ink)


def _apply_column_style(ax, ctx, max_val: float = 100.0, statistic: str = "pct") -> None:
    """Apply house-style spines, grid, and tick formatting to a column axes."""
    _ink, muted, grid = chart_furniture(ctx)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)

    ax_max, y_ticks = _value_axis(max_val, statistic)
    for yv in y_ticks:
        if yv > 0:
            ax.axhline(yv, color=grid, lw=0.8, zorder=1)

    ax.tick_params(axis="x", length=0)
    ax.tick_params(axis="y", length=0)

    ax.set_yticks(y_ticks)
    ax.set_yticklabels([_tick_text(v) for v in y_ticks], fontsize=9.5, color=muted)
    ax.set_ylim(0, ax_max)
    apply_axis_titles(ax, ctx.spec, _ink)


def _label_offset(max_val: float) -> float:
    """Small positive offset for data labels (proportional to axis range)."""
    return max(0.5, max_val * 0.01)


def _grouped_offsets(segs, segment_primary, cluster_w: float = 0.82):
    """Cross-tab (segment_primary set): return (offsets, bar_width, groups) where a bar
    for each segment is positioned with an EXTRA gap between primary-classifier groups —
    so the bars are pulled apart by primary (Mies · · · | gap | Nainen · · ·). `offsets`
    are relative to a category centre; the whole cluster spans ~`cluster_w`. Returns None
    when not a cross-tab (single-classifier layout is unchanged)."""
    if not segment_primary or len(segs) < 2:
        return None
    groups = [segment_primary.get(s, s) for s in segs]
    if len(set(groups)) < 2:
        return None
    GAP = 0.7                      # extra space (in bar-slot units) between groups
    centers, pos, prev = [], 0.0, None
    for g in groups:
        if prev is not None and g != prev:
            pos += GAP
        centers.append(pos + 0.5)
        pos += 1.0
        prev = g
    scale = cluster_w / pos
    offsets = [(c - pos / 2.0) * scale for c in centers]
    return offsets, scale * 0.9, groups


def _grouped_stacked_positions(cats, segment_primary):
    """Stacked cross-tab: absolute bar positions for each cat (= a combo) grouped by
    primary with a gap, plus [(primary_label, group_centre), …] for group labels.
    None when not a cross-tab (single-classifier stacked layout is unchanged)."""
    if not segment_primary:
        return None
    groups = [segment_primary.get(c, c) for c in cats]
    if len(set(groups)) < 2:
        return None
    GAP = 0.8
    positions, pos, prev, spans = [], 0.0, None, {}
    for c, g in zip(cats, groups):
        if prev is not None and g != prev:
            pos += GAP
        positions.append(pos)
        spans.setdefault(g, []).append(pos)
        pos += 1.0
        prev = g
    labels = [(g, (min(p) + max(p)) / 2.0) for g, p in spans.items()]
    return positions, labels


def _secondary_tick(cat: str) -> str:
    """From a combo label 'Primary · Secondary' → 'Secondary' (the per-bar tick in a
    grouped cross-tab, where the primary is shown once as a group label)."""
    return cat.split(" · ", 1)[1] if " · " in cat else cat


def _resolve_xtab_layout(ctx):
    """For a cross-tab (segment_primary present), resolve the effective layout —
    'grouped', 'small_multiples', or 'separate' (explicit only — 'auto' never
    resolves to it; separate mode is opted into via `xtab_layout` in the spec).
    Returns None when not a cross-tab. 'auto' groups when the combo count is
    small enough to stay legible, else uses panels."""
    sp = getattr(ctx.series, "segment_primary", None)
    if not sp:
        return None
    mode = (getattr(ctx.spec, "options", None) or {}).get("xtab_layout", "auto")
    if mode in ("grouped", "small_multiples", "separate"):
        return mode
    n_combos = len(ctx.series.segments)
    n_primary = len(set(sp.values()))
    return "small_multiples" if (n_primary >= 2 and n_combos > 8) else "grouped"


def _primary_groups(series):
    """Ordered [(primary_label, [combo_segment, …]), …] from segment_primary."""
    sp = series.segment_primary or {}
    order, by_primary = [], {}
    for s in series.segments:
        p = sp.get(s, s)
        if p not in by_primary:
            order.append(p)
            by_primary[p] = []
        by_primary[p].append(s)
    return [(p, by_primary[p]) for p in order]


def _drawable_panels(groups, drawable) -> list[tuple[str, list[str]]]:
    """`groups` (from `_primary_groups`, which sees EVERY segment) narrowed to the
    series that will actually be drawn, with panels that keep none dropped entirely.

    `_primary_groups` reads `series.segments`, but `series_values`/`_stacked_layout`
    drop segments computed on a near-empty base (MIN_SEGMENT_BASE) and a hidden
    "Total". Zipping the two together gives a panel that is titled and legended but
    holds only 0-height bars — a phantom reading "0 %". The design says such a panel
    vanishes, so it does.

    Only the SEPARATE renderers use this: each of their panels is a whole classifying
    VARIABLE with its own colours and its own legend, so dropping one loses nothing
    the reader could have cross-referenced. Small multiples share one colour ramp and
    one legend across panels, keyed by position — filtering there would shift a
    panel's colours out of step with its siblings.

    Never returns an empty list in practice: every key of `drawable` comes from
    `series.segments`, so at least the panel that owns it survives.
    (spec 2026-08-04, final review I3/I4)"""
    kept = [(p, [s for s in segs if s in drawable]) for p, segs in groups]
    return [(p, segs) for p, segs in kept if segs]


def _render_small_multiples(ctx, cats, *, vertical: bool) -> None:
    """Cross-tab SMALL MULTIPLES: one subplot per PRIMARY value, each a clustered bar of
    (answer categories × the SECONDARY classifier). Shared value axis + one legend."""
    from matplotlib.patches import Patch
    series = ctx.series
    groups = _primary_groups(series)
    _c, _s, data = series_values(series)
    n_cat = len(cats)
    n_sec = max((len(segs) for _p, segs in groups), default=1)
    clrs = series_colors(n_sec, palette=template_palette(ctx),
                          accent=chart_accent(ctx))
    all_vals = [v for _p, segs in groups for s in segs for v in data.get(s, []) if v is not None]
    max_val = max(all_vals, default=0.0)
    ink, _muted, _grid = chart_furniture(ctx)

    if vertical:
        fig, axes = new_figure_grid(ctx, len(groups))
        x = np.arange(n_cat)
        for ax, (p, segs) in zip(axes, groups):
            n = len(segs)
            w = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * w if n > 1 else 0.0
                ax.bar(x + off, [v or 0.0 for v in vals], width=w, color=clrs[i],
                       edgecolor="none", zorder=3)
            ax.set_title(p, fontsize=12.5, fontweight="bold", color=ink, pad=6)
            ax.set_xticks(x)
            ax.set_xticklabels([_wrap_xtick_label(c) for c in cats], fontsize=8.5,
                               color=ink, rotation=_XTICK_ROTATION, ha="right",
                               rotation_mode="anchor")
            _apply_column_style(ax, ctx, max_val, series.statistic)
    else:
        fig, axes = new_figure_grid(ctx, len(groups), tall_in=n_cat * 0.42 + 2.0)
        y = np.arange(n_cat)[::-1]
        for k, (ax, (p, segs)) in enumerate(zip(axes, groups)):
            n = len(segs)
            h = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * h if n > 1 else 0.0
                ax.barh(y + off, [v or 0.0 for v in vals], height=h, color=clrs[i],
                        edgecolor="none", zorder=3)
            ax.set_title(p, fontsize=12.5, fontweight="bold", color=ink, pad=6)
            ax.set_yticks(y)
            _apply_bar_style(ax, ctx, max_val, series.statistic)
            # y-axis is SHARED (sharey) → set the category labels ONCE, then hide their
            # DISPLAY on the other panels (clearing them would clear the shared axis).
            if k == 0:
                ax.set_yticklabels([_wrap_label(c) for c in cats], fontsize=9, color=ink)
            ax.tick_params(axis="y", labelleft=(k == 0))

    if ctx.spec.elements.legend:
        sec = [_secondary_tick(s) for s in groups[0][1]]
        handles = [Patch(facecolor=clrs[i], edgecolor="none") for i in range(len(sec))]
        fig.legend(handles, sec, loc="lower center", ncol=min(len(sec), 6),
                   frameon=False, fontsize=10, bbox_to_anchor=(0.5, 0.0))
    fig.subplots_adjust(bottom=0.24, wspace=0.12, top=0.9,
                        left=0.12 if vertical else 0.2)
    place_picture(ctx, render_png(fig))


def _measure_max_label_width_in(labels: list[str], fontsize: float, *,
                                 rotation: float = 0.0, dpi: float = 200.0) -> float:
    """The widest rendered footprint of `labels` at `fontsize` pt, in INCHES —
    measured with real matplotlib text layout, not estimated from a character
    count.

    Builds a throwaway Agg figure (created, measured, and discarded — never
    saved to a file), places each label as a `Text` artist at `rotation`
    degrees (matching `Text`'s own rotation convention, so a rotated label's
    on-screen footprint — including any wrapped newlines — is measured
    correctly, not just its unrotated string width), reads its true layout
    box via `text.get_window_extent(renderer)` — matplotlib's own font-metric
    engine, which accounts for the actual glyphs, kerning, and multi-line
    extent — and converts the widest box from pixels to inches using `dpi`
    (the same dpi the real chart is saved at, so the two agree).
    """
    if not labels:
        return 0.0
    register_fonts()
    fig = _new_agg_figure(6.0, 4.0, dpi=dpi)
    renderer = fig.canvas.get_renderer()
    widest_px = 0.0
    for label in labels:
        text = fig.text(0.5, 0.5, label, fontsize=fontsize, rotation=rotation)
        widest_px = max(widest_px, text.get_window_extent(renderer).width)
    return float(widest_px) / dpi


# Small buffer between a measured label block and whatever it sits against
# (the axis spine/tick mark on one side, the neighbouring axes' edge on the
# other) so a label doesn't visually kiss the plot or its neighbour even when
# sized exactly to the label's own measured width.
_LABEL_PAD_IN: float = 0.12
# Fixed right-hand figure margin: nothing in this layout draws a label at the
# figure's right edge (the rightmost panel's value-axis lives INSIDE its own
# axes), so this only needs to clear the outermost tick mark, not a label.
_RIGHT_MARGIN_IN: float = 0.15
# Floor for the width actually left to DRAW bars once a horizontal panel's
# label gutter/gap is subtracted from its side-by-side share. A 0-100% value
# axis needs enough width for bar-length differences of a few points to read
# as visually distinct; below this floor two side-by-side panels would each
# be a stamp, so stacking (full width, half height per panel) is the more
# legible choice. Chosen, not derived: ~1/4 of the 9in figure-width floor,
# i.e. still noticeably more than a bare tick-label's width (~0.2in).
_MIN_HGUTTER_PLOT_IN: float = 2.2


def _side_by_side_layout(fig_w_in: float, n_panels: int,
                          left_label_w_in: float, gap_label_w_in: float
                          ) -> tuple[float, float, float, float]:
    """The (left_frac, right_frac, wspace_frac, plot_w_in) matplotlib needs
    to actually draw `n_panels` EQUAL-width side-by-side axes without any
    panel's OWN tick labels overflowing onto a neighbour.

    This is the single source of truth for BOTH the side-by-side FIT
    DECISION (`_stack_panels` and `_render_stacked_variable_panels` compare
    the returned `plot_w_in` against `_MIN_HGUTTER_PLOT_IN`) and the actual
    render call's `subplots_adjust(left=..., right=..., wspace=...)` — ALL
    THREE returned fractions must be passed to that call, not just
    `left`/`wspace`: `right_frac` is part of the same span arithmetic
    `wspace_frac` was solved against, and matplotlib's default `right`
    (0.9) is not it — passing only two of the three silently narrows the
    real span below what `wspace_frac` assumed, undersizing the very gap
    this function computed to prevent overlap. (This exact omission was
    caught in review: `plot_w_in` and `wspace_frac` looked right on paper,
    but the figure that actually got saved used matplotlib's default
    `right=0.9` instead of this function's `right_frac`, so the real
    available span was narrower than what `wspace_frac` was sized for, and
    a panel's label bled into its neighbour anyway.)

    Matplotlib draws y/x-tick labels OUTSIDE their own axes, extending to
    the axes' own left: panel 0's own labels land in the figure's `left`
    margin, and panel 1's own labels land in the GAP between panel 0 and 1
    (`wspace`) — never inside their own axes' bounding box, so a
    too-narrow margin/gap lands the label ON TOP OF THE NEIGHBOUR'S bars.

    `left_label_w_in` / `gap_label_w_in` are the pre-measured (already
    wrapped/rotated exactly as the real chart draws them) max label width
    for whichever panel draws INTO that margin/gap — 0.0 when that panel
    draws no label of its own there (e.g. a shared-y-axis clustered
    renderer, where only panel 0 ever shows a label at all).

    `wspace` is matplotlib's own unit: a fraction of the MEAN AXES WIDTH,
    not of the figure (`matplotlib.figure.SubplotParams`) — and that axes
    width is exactly what this function solves for, so it can't be produced
    by a simple division of a target gap-in-inches. Solved directly instead
    of iterated: with `n_panels` equal-width axes of width `w` (inches) and
    `n_panels - 1` gaps of `gap_in` inches between them, the total span
    available for axes + gaps is `(right_frac - left_frac) * fig_w_in =
    n_panels * w + (n_panels - 1) * gap_in` — a single division for `w`,
    no fixed point.
    """
    n_panels = max(n_panels, 1)
    left_frac = (left_label_w_in + _LABEL_PAD_IN) / fig_w_in
    right_frac = 1.0 - (_RIGHT_MARGIN_IN / fig_w_in)
    gap_in = (gap_label_w_in + _LABEL_PAD_IN) if n_panels > 1 else 0.0
    span_in = max(0.0, (right_frac - left_frac) * fig_w_in)
    plot_w_in = (span_in - (n_panels - 1) * gap_in) / n_panels
    wspace_frac = (gap_in / plot_w_in) if (n_panels > 1 and plot_w_in > 0) else 0.12
    return left_frac, right_frac, wspace_frac, plot_w_in


def _stack_panels(cats: list[str], *, fig_w_in: float, fontsize: float,
                   vertical: bool, n_panels: int = 2,
                   shared_labels: bool = True) -> bool:
    """True when SEPARATE panels should sit one above the other rather than
    side by side.

    SIDE BY SIDE IS THE DEFAULT. Stacking is the exception, chosen only when
    `cats` — wrapped exactly as the real chart wraps them (`_wrap_label` for
    the horizontal left-gutter, `_wrap_xtick_label` + `_XTICK_ROTATION` for
    the rotated vertical x-axis) and measured at the real `fontsize` via
    `_measure_max_label_width_in` (actual matplotlib text metrics, not a
    character count) — demonstrably do not fit `n_panels` panels side by side
    across a `fig_w_in`-wide figure. The room available is computed by
    `_side_by_side_layout` — the SAME function the render call uses to size
    `subplots_adjust(left=..., wspace=...)`, so this decision and the actual
    layout can never disagree.

    HORIZONTAL panels: category labels sit in each panel's left gutter.
    `shared_labels=True` (the default, matching `_render_variable_panels`'s
    shared-y-axis clustered renderer) means only panel 0 ever draws `cats` as
    a label, so only the figure's `left` margin needs to fit it — `False`
    means every panel draws its own copy (not used by any current caller of
    THIS convenience wrapper; `_render_stacked_variable_panels` has genuinely
    different per-panel label sets and computes its own layout directly
    instead, per-panel, rather than through this cats-only entry point).
    Below `_MIN_HGUTTER_PLOT_IN` of resulting plot width, the panels stack.

    VERTICAL panels: category labels sit on the shared x-axis, rotated by
    `_XTICK_ROTATION`, and EVERY panel draws its own copy of the same `cats`
    (so both the left margin and the inter-panel gap need to fit them). The
    binding constraint is `len(cats)` labels arrayed side by side across the
    resulting per-panel plot width — if the widest rotated label footprint
    exceeds `plot_w_in / len(cats)`, neighbouring ticks within one panel
    would overlap each other, so the panels stack. (This is where category
    COUNT still matters — but as a divisor against measured plot width, not
    a bare `> 6`.)
    (spec 2026-08-04; revised for runtime measurement 2026-08-06; layout
    unified with `_side_by_side_layout` 2026-08-06)"""
    if vertical:
        wrapped = [_wrap_xtick_label(c) for c in cats]
        label_w_in = _measure_max_label_width_in(wrapped, fontsize, rotation=_XTICK_ROTATION)
        _left, _right, _wspace, plot_w_in = _side_by_side_layout(
            fig_w_in, n_panels, label_w_in, label_w_in)
        per_cat_in = plot_w_in / max(len(cats), 1)
        return bool(label_w_in > per_cat_in)
    wrapped = [_wrap_label(c) for c in cats]
    label_w_in = _measure_max_label_width_in(wrapped, fontsize, rotation=0.0)
    gap_w_in = 0.0 if shared_labels else label_w_in
    _left, _right, _wspace, plot_w_in = _side_by_side_layout(
        fig_w_in, n_panels, label_w_in, gap_w_in)
    return bool(plot_w_in < _MIN_HGUTTER_PLOT_IN)


def _render_variable_panels(ctx, cats, *, vertical: bool) -> None:
    """SEPARATE layout: one panel per classifying VARIABLE, each an ordinary
    clustered bar of (answer categories x that variable's groups).

    Unlike small multiples the panels do NOT share a series axis — panel 1 shows
    gender's groups, panel 2 age's — so each carries its own legend and its own
    colours, restarting at index 0. A shared ramp would imply "Nainen" and
    "Nuoret" correspond. The VALUE axis is shared so the bars stay comparable.
    (spec 2026-08-04-separate-classifier-panels)"""
    from matplotlib.patches import Patch
    series = ctx.series
    _c, _s, data = series_values(series)
    # A variable whose every group fell under MIN_SEGMENT_BASE has nothing to draw;
    # its panel is omitted rather than rendered as titled, legended 0 % bars.
    groups = _drawable_panels(_primary_groups(series), data)
    n_cat = len(cats)
    fig_w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    # fontsize matches the ACTUAL y/x-tick label fontsize set below (9.0 for the
    # horizontal left-gutter, 8.5 for the vertical rotated x-axis) so the fit
    # test measures the labels at the size they will really be drawn at.
    panel_fontsize = 8.5 if vertical else 9.0
    n_candidate = len(groups)
    rows = 2 if _stack_panels(list(cats), fig_w_in=fig_w_in, fontsize=panel_fontsize,
                              vertical=vertical, n_panels=n_candidate) else 1
    # `cols` mirrors `new_figure_grid`'s own ceil(n / rows) so the margin/gap
    # computed below matches the grid that actually gets built.
    cols = max(1, -(-n_candidate // rows))
    # The SAME measurement `_stack_panels` used for the fit decision, reused
    # here (not passed through — `_stack_panels` stays a cats-in/bool-out
    # unit so its existing tests keep working) to size the ACTUAL
    # `subplots_adjust` margins via `_side_by_side_layout` — the fit decision
    # and the space allocation must agree, or a panel measured as "fits" can
    # still render with a too-narrow margin and overflow onto its neighbour.
    if vertical:
        panel_label_w_in = _measure_max_label_width_in(
            [_wrap_xtick_label(c) for c in cats], panel_fontsize, rotation=_XTICK_ROTATION)
        # Every panel draws its OWN copy of the same rotated `cats` (no
        # shared axis on the x-side), so both the left margin and the
        # inter-panel gap need to fit it.
        gap_label_w_in = panel_label_w_in
    else:
        panel_label_w_in = _measure_max_label_width_in(
            [_wrap_label(c) for c in cats], panel_fontsize, rotation=0.0)
        # sharey=True means only the leftmost panel of each row ever DISPLAYS
        # a label (see `first_in_row` below) — no other panel draws one, so
        # no inter-panel gap needs to accommodate one.
        gap_label_w_in = 0.0
    left_frac, right_frac, wspace_frac, _plot_w_in = _side_by_side_layout(
        fig_w_in, cols, panel_label_w_in, gap_label_w_in)
    all_vals = [v for _p, segs in groups for s in segs for v in data.get(s, [])
                if v is not None]
    max_val = max(all_vals, default=0.0)
    tall = n_cat * 0.42 + 2.0
    # Vertical (column) panels: height does NOT scale with n_cat the way the
    # horizontal `tall` term does — categories sit on the shared x-axis, so more
    # of them widen a panel, not tallen it. What DOES need height per row is each
    # panel's own rotated/wrapped x-tick label band plus its own legend below it.
    # The un-stacked (rows == 1) case already renders cleanly at the 4.5in
    # `new_figure`/`new_figure_grid` default — that default is exactly the height
    # `_render_column_v` (build_image_column's un-stacked path) already uses for a
    # plot + rotated x-ticks + one legend band, the same ingredients each panel
    # here has. So 4.5in is a validated per-row budget; when panels stack
    # (rows == 2) each row needs its own copy of it, so multiply by `rows`.
    # Leave it None for rows == 1 to keep that already-correct sizing untouched.
    v_tall = 4.5 * rows if rows > 1 else None
    fig, axes = new_figure_grid(ctx, len(groups),
                                tall_in=(tall * rows if not vertical else v_tall),
                                rows=rows)
    ink, _muted, _grid = chart_furniture(ctx)

    for k, (ax, (p, segs)) in enumerate(zip(axes, groups)):
        n = len(segs)
        clrs = series_colors(n, palette=template_palette(ctx),
                              accent=chart_accent(ctx))
        if vertical:
            x = np.arange(n_cat)
            w = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * w if n > 1 else 0.0
                ax.bar(x + off, [v or 0.0 for v in vals], width=w, color=clrs[i],
                       edgecolor="none", zorder=3)
            ax.set_xticks(x)
            ax.set_xticklabels([_wrap_xtick_label(c) for c in cats], fontsize=8.5,
                               color=ink, rotation=_XTICK_ROTATION, ha="right",
                               rotation_mode="anchor")
            _apply_column_style(ax, ctx, max_val, series.statistic)
        else:
            y = np.arange(n_cat)[::-1]
            h = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * h if n > 1 else 0.0
                ax.barh(y + off, [v or 0.0 for v in vals], height=h, color=clrs[i],
                        edgecolor="none", zorder=3)
            ax.set_yticks(y)
            _apply_bar_style(ax, ctx, max_val, series.statistic)
            # The y-axis is SHARED (sharey=True in new_figure_grid), so all axes
            # share ONE tick formatter/label set — calling set_yticklabels once at
            # k==0 propagates to every panel; `labelleft` then controls only which
            # panel's axis actually DISPLAYS that shared text (clearing the labels
            # instead would blank the shared axis for every panel, not just one).
            # When stacked (rows == 2), `cols` (len(groups) // rows) is 1 today —
            # this layout always has exactly TWO classifying variables, so each
            # row holds exactly one panel and is its own leftmost column. That
            # collapses "leftmost of each row" to "every panel", hence `True`
            # unconditionally here. This assumption breaks silently (duplicate
            # labels drawn on non-leftmost columns) if a THIRD classifying
            # variable is ever added and cols > 1 while rows > 1.
            first_in_row = (k == 0) if rows == 1 else True
            if k == 0:
                ax.set_yticklabels([_wrap_label(c) for c in cats], fontsize=9, color=ink)
            ax.tick_params(axis="y", labelleft=first_in_row)
        # Each panel is titled with its VARIABLE, not with a group of the first one.
        ax.set_title(p, fontsize=12.5, fontweight="bold", color=ink, pad=6)
        if ctx.spec.elements.legend:
            names = [_secondary_tick(s) for s in segs]
            handles = [Patch(facecolor=clrs[i], edgecolor="none") for i in range(len(names))]
            ax.legend(handles, names, loc="upper center", bbox_to_anchor=(0.5, -0.12),
                      ncol=min(len(names), 4), frameon=False, fontsize=9)

    fig.subplots_adjust(bottom=0.24, wspace=wspace_frac, hspace=0.45, top=0.9,
                        left=left_frac, right=right_frac)
    place_picture(ctx, render_png(fig))


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
    layout = _resolve_xtab_layout(ctx)
    if layout == "separate":
        _render_variable_panels(ctx, cats, vertical=True)
        return
    if layout == "small_multiples":
        _render_small_multiples(ctx, cats, vertical=True)
        return
    _render_column_v(ctx, cats, segs, data)


def _render_column_v(ctx, cats, segs, data) -> None:
    """Internal vertical-bar renderer."""
    fig, ax = new_figure(ctx)
    clrs = series_colors(len(segs), palette=template_palette(ctx),
                          accent=chart_accent(ctx))

    n_cats = len(cats)
    n_segs = len(segs)
    x = np.arange(n_cats)
    width = 0.7 / n_segs if n_segs > 1 else 0.5

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=0.0)
    ink, _muted, _grid = chart_furniture(ctx)

    # Cross-tab: pull the bars apart into primary-classifier groups (gap between groups).
    grouped = _grouped_offsets(segs, ctx.series.segment_primary)

    for i, seg in enumerate(segs):
        vals = data[seg]
        if grouped:
            offset, bwidth = grouped[0][i], grouped[1]
        else:
            offset = (i - n_segs / 2 + 0.5) * width if n_segs > 1 else 0.0
            bwidth = width
        # R4.2: "Not answered" bar gets MUTED grey; all others get the series colour.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in cats]
        bars = ax.bar(
            x + offset, vals, width=bwidth,
            label=seg, color=bar_clrs, edgecolor="none", zorder=3,
        )
        off = _label_offset(max_val)
        # Per-bar value labels collide once columns get narrow (many segments) —
        # suppress them past a threshold and rely on the axis grid + legend.
        for bar, v in zip(bars, vals):
            if v is not None and n_segs <= _MAX_LABELED_SEGMENTS_V:
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + off,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    ha="center", va="bottom",
                    fontsize=9.5, fontweight="bold", color=ink, zorder=5,
                )

    # Wrap + rotate x-axis labels so they are shown in full and never overlap.
    display_cats = [_wrap_xtick_label(c) for c in cats]
    ax.set_xticks(x)
    ax.set_xticklabels(
        display_cats, fontsize=10.5, color=ink,
        rotation=_XTICK_ROTATION, ha="right", rotation_mode="anchor",
    )
    _apply_column_style(ax, ctx, max_val, ctx.series.statistic)

    if ctx.spec.elements.legend and n_segs > 1:
        _place_series_legend(fig, ax, segs, ctx, vertical=True)

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# build_image_bar  (horizontal bars — always horizontal)
# ---------------------------------------------------------------------------

def build_image_bar(ctx) -> None:
    """Horizontal grouped bar chart with house style (REQ-C-24b/f, REQ-C-27a)."""
    cats, segs, data = series_values(ctx.series)
    layout = _resolve_xtab_layout(ctx)
    if layout == "separate":
        _render_variable_panels(ctx, cats, vertical=False)
        return
    if layout == "small_multiples":
        _render_small_multiples(ctx, cats, vertical=False)
        return
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
    clrs = series_colors(len(segs), palette=template_palette(ctx),
                          accent=chart_accent(ctx))

    n_segs = len(segs)
    y = np.arange(n_cats)[::-1]   # top category at top of plot
    height = 0.7 / n_segs if n_segs > 1 else 0.62

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=0.0)
    ink, _muted, _grid = chart_furniture(ctx)

    # Cross-tab: pull the bars apart into primary-classifier groups (gap between groups).
    grouped = _grouped_offsets(segs, ctx.series.segment_primary)

    for i, seg in enumerate(segs):
        vals = data[seg]
        if grouped:
            offset, height = grouped[0][i], grouped[1]
        else:
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
    # Auto-fit, unless somebody has said otherwise.
    #
    # The row label size is computed from how many categories there are and how
    # tall the slot is, clamped to 8.5-11.5pt. That is right until it is not:
    # the reported slide had nine long statements whose labels ran into each
    # other at the floor of that range, and no amount of auto-fitting reads a
    # sentence into 0.4in. A template's own `content` size, set by an author who
    # can see the result, wins outright — including when it is smaller than the
    # clamp would ever choose.
    ylabel_fs = max(8.5, min(11.5, row_pt / (max_lines * 1.3)))
    chosen_pt = _explicit_label_pt(ctx)
    if chosen_pt:
        ylabel_fs = chosen_pt
    # Scale the value-label font to a SINGLE BAR's height (which shrinks as segments
    # multiply — a two-classifier cross-tab packs many thin bars per row), so the
    # label stays a bit smaller than the bar and never touches its neighbours.
    per_bar_pt = row_pt * (0.7 / n_segs if n_segs > 1 else 0.62)
    value_fs = max(5.5, min(9.5, per_bar_pt * 0.9))

    off = _label_offset(max_val)
    for i, seg in enumerate(segs):
        vals = data[seg]
        offset = (i - n_segs / 2 + 0.5) * height if n_segs > 1 else 0.0
        ys = y + offset
        for yi, v in zip(ys, vals):
            if v is not None and per_bar_pt >= _MIN_LABEL_BAR_PT:
                ax.text(
                    v + off, yi,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    va="center", ha="left",
                    fontsize=value_fs, fontweight="bold", color=ink, zorder=5,
                )

    # Wrap y-axis labels; cap to the lines that fit the band (ellipsis last resort).
    display_cats = [
        wrap_label_capped(c, _HBAR_LABEL_WRAP_WIDTH, max_lines) for c in cats
    ]
    ax.set_yticks(y)
    ax.set_yticklabels(display_cats, fontsize=ylabel_fs, color=ink)
    ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
    _apply_bar_style(ax, ctx, max_val, ctx.series.statistic)

    if ctx.spec.elements.legend and n_segs > 1:
        _place_series_legend(fig, ax, segs, ctx, vertical=False)

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
    segment and the STACK is the question's answer categories. For a single-choice
    question the engine's per-segment percentages sum to 100 within a segment
    (column %), so each bar fills exactly 100% — no floating 'Total'. A
    multi-response question does NOT: its option shares overlap and sum far past
    100, which is why the drawing step asks `_stack_scaling` whether it may
    normalise at all. Returns (bars, stack, data) where
    data[stack_member] = [value per bar].

    With no classifier (segments == ('Total',)) there is nothing to split by, so
    the single 'Total' column IS the one bar and the answer categories become its
    stack — the classic single 100%-stacked distribution bar (the "just total"
    case).
    """
    cats, segs, data = series_values(series)
    real = [s for s in segs if s != "Total"]
    if not real:
        # No classifier: one 'Total' bar, stacked by the answer categories.
        bars = ["Total"]
    elif "Total" in segs:
        # Classified + show_total: append the overall distribution as a reference
        # "Total" bar (series_values already dropped it when show_total is off).
        bars = real + ["Total"]
    else:
        bars = real
    stack = cats
    new_data = {
        qcat: [data[seg][ci] for seg in bars] for ci, qcat in enumerate(cats)
    }
    return bars, stack, new_data


def _bar_is_measurable(series, bar) -> bool:
    """Whether `is_partition` can actually JUDGE this bar, i.e. whether a False
    from it would be evidence of overlap rather than of missing information.

    It needs a non-zero base and, for every category, a cell carrying a count or
    a percentage. A mean-statistic stack (cells hold only `mean`), a zero base or
    a hole in the cell grid says nothing about overlap, so such a bar must not be
    the reason a whole chart abandons the 100% reading."""
    if not series.base_n.get(bar):
        return False
    cells = [series.cells.get((c, bar)) for c in series.categories]
    if not cells or any(c is None for c in cells):
        return False
    return (all(c.count is not None for c in cells)
            or all(c.pct is not None for c in cells))


def _stack_scaling(series, bars, stack, data) -> tuple[bool, float]:
    """Decide, ONCE PER CHART, how a stacked chart's bars are scaled. Returns
    (normalise, axis_max).

    normalise=True — each bar's segments are scaled to fill exactly 100 (the
    100%-stacked reading) against a 0-100 value axis. Honest only where the stack
    really partitions each bar's base: then normalising just absorbs the ±1 of
    rounding, and the drawn shape agrees with the printed numbers.

    normalise=False — the TRUE values are drawn and the value axis carries the
    real maximum. This is the multi-response case: respondents pick several
    options, so the shares sum to far more than 100 (mat-erisan2/var7: 465%) and
    normalising would draw a segment LABELLED "85 %" at 18% of the bar. The
    printed number would be true and the picture false; a plain stacked bar is
    the honest reading of the same data (and is what the native export already
    emits — BAR_STACKED, not BAR_STACKED_100).

    Per CHART, not per bar: mixing a normalised bar with a true-width one in the
    same axes makes the two incomparable, which is worse than either alone. One
    measurable bar that materially overshoots therefore draws every bar true.

    The predicate is `SeriesResult.is_partition` with the SAME asymmetric
    allowance the offering side gives a pie (`PARTITION_UNDERSHOOT_TOL_PCT`):
    falling a couple of points short of 100 is a small unnamed "no answer" slice
    and keeps normalising exactly as before; overshoot is overlap and gets no
    slack. Bars `is_partition` cannot judge (see `_bar_is_measurable`) keep the
    100% reading."""
    normalise = all(
        series.is_partition(b, undershoot_tol=PARTITION_UNDERSHOOT_TOL_PCT)
        for b in bars if _bar_is_measurable(series, b)
    )
    if normalise:
        return True, 100.0
    totals = [sum(data[s][i] or 0.0 for s in stack) for i in range(len(bars))]
    return False, max(totals, default=0.0)


def _render_stacked_variable_panels(ctx, cats) -> None:
    """SEPARATE layout for the stacked types: one stacked panel per classifying
    VARIABLE (100%-stacked where the data allows it — see `_stack_scaling`). The
    stacked builders have no panel path of their own — they only draw the
    grouped/rotated-primary layout — so this is the panel equivalent.

    Decision, not an oversight: `build_image_column_stacked` (the VERTICAL 100%-
    stacked type) also calls this HORIZONTAL panel renderer. A 100% stack reads the
    same either way — the composition is what matters, not the axis — and the
    panel titles already carry the variable, so a dedicated vertical layout would
    duplicate this one for no legible gain. (spec 2026-08-04-separate-classifier-panels)
    """
    series = ctx.series
    bars_all, stack, data = _stacked_layout(series)
    # Decided across ALL panels' bars, and the axis maximum shared by every panel:
    # panels of one chart are read against each other, so they must not scale
    # independently. (See `_stack_scaling`.)
    normalise, axis_max = _stack_scaling(series, bars_all, stack, data)
    # `bars_all` is base-filtered; a variable whose every group is near-empty keeps
    # no bar at all, and a panel with no bars used to reach `min(y)` on an empty
    # sequence (ValueError). It is omitted instead. (final review I3)
    groups = _drawable_panels(_primary_groups(series), bars_all)
    clrs = scale_colors(len(stack), chart_accent(ctx))                 # the stack is the shared scale
    fig_w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    # Each panel's OWN bar labels (the classifier's own group names, via
    # `_secondary_tick`), measured PER PANEL rather than flattened into one
    # global list: panel 0's labels only need to fit the figure's LEFT
    # margin, panel 1's only need to fit the GAP between panel 0 and 1 (see
    # `_side_by_side_layout`) — sharey=False means every panel draws its own
    # labels, unlike the clustered renderer's shared y-axis. Measured at
    # fontsize=10.5 to match the real `ax.set_yticklabels(...)` call below.
    panel_label_w_in = [
        _measure_max_label_width_in(
            [_wrap_label(_secondary_tick(b)) for b in bars], 10.5)
        for _p, bars in groups
    ]
    n_candidate = len(groups)
    left0_w_in = panel_label_w_in[0] if panel_label_w_in else 0.0
    gap1_w_in = panel_label_w_in[1] if n_candidate > 1 else 0.0
    _left_sbs, _right_sbs, _wspace_sbs, plot_w_in = _side_by_side_layout(
        fig_w_in, n_candidate, left0_w_in, gap1_w_in)
    rows = 2 if plot_w_in < _MIN_HGUTTER_PLOT_IN else 1
    # `cols` mirrors `new_figure_grid`'s own ceil(n / rows).
    cols = max(1, -(-n_candidate // rows))
    if cols > 1:
        left_frac, right_frac, wspace_frac, _plot_w = _side_by_side_layout(
            fig_w_in, cols, left0_w_in, gap1_w_in)
    else:
        # One column: every row draws its OWN labels, but `subplots_adjust`'s
        # `left` is a single figure-wide margin shared by every row — so it
        # must fit the WIDEST label across ALL panels, not just panel 0's.
        # No inter-panel gap exists (one column), so wspace is unused.
        widest_w_in = max(panel_label_w_in, default=0.0)
        left_frac, right_frac, wspace_frac, _plot_w = _side_by_side_layout(
            fig_w_in, 1, widest_w_in, 0.0)
    flat_vals = [v for seg in stack for v in data[seg] if v is not None]
    max_bars = max((len(segs) for _p, segs in groups), default=1)
    # Own budget, not the clustered renderer's: each row here is ONE full-width
    # 100%-stack bar (no clustering within a row), the same shape of problem the
    # plain horizontal-bar builder solves with `_HBAR_ROW_IN` (0.52in — enough for a
    # bar plus up to 2 wrapped label lines). `+2.0` is the same fixed chrome budget
    # (title + value axis + legend margins) `_render_variable_panels` validates for
    # its horizontal branch. When panels stack (rows == 2) each row needs its own
    # copy of that budget, so the whole thing is multiplied by `rows`.
    tall_in = (max_bars * _HBAR_ROW_IN + 2.0) * rows
    fig, axes = new_figure_grid(ctx, len(groups), tall_in=tall_in, rows=rows,
                                sharey=False)   # panels draw DIFFERENT bars, not a shared axis
    ink, _muted, _grid = chart_furniture(ctx)

    for ax, (p, bars) in zip(axes, groups):
        # `bars_all` (from `_stacked_layout`) is base-filtered and may drop a
        # near-empty group's bar, so `_drawable_panels` already narrowed each panel
        # to its surviving bars. They are re-indexed against `bars_all`, not the raw
        # `series.segments`, so a filtered-out bar can never misalign the rest (see
        # `new_figure_grid`'s sharey note for the sibling pitfall this mirrors:
        # trusting a helper's implicit assumptions without checking them).
        idx = [bars_all.index(b) for b in bars]
        panel = {s: [data[s][i] for i in idx] for s in stack}
        y = np.arange(len(bars))[::-1]
        _draw_stacked_panel(ax, bars, stack, panel, clrs, ctx, y, flat_vals,
                            normalise=normalise, axis_max=axis_max)
        ax.set_yticks(y)
        ax.set_yticklabels([_wrap_label(_secondary_tick(b)) for b in bars],
                           fontsize=10.5, color=ink)
        ax.tick_params(axis="y", labelleft=True)
        ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
        _apply_bar_style(ax, ctx, axis_max, "pct" if normalise else series.statistic)
        ax.set_title(p, fontsize=12.5, fontweight="bold", color=ink, pad=6)
        # per panel, keyed by bar — placed against the axis the bars were drawn on
        _draw_row_summary(ctx, ax, y, bars, ax.get_xlim()[1])

    if ctx.spec.elements.legend and len(stack) > 1:
        _legend_below(axes[-1], len(stack), ctx)
    fig.subplots_adjust(bottom=0.24, wspace=wspace_frac, hspace=0.45, top=0.9,
                        left=left_frac, right=right_frac)
    place_picture(ctx, render_png(fig))


def build_image_column_stacked(ctx) -> None:
    """Stacked vertical bar chart: bars = classifier segments, stack = answer
    categories (house style). Normalised to 100% per column where the stack really
    partitions the column's base, otherwise drawn at true heights
    (`_stack_scaling`) — the horizontal builder's rule, applied to columns."""
    cats, segs, data = _stacked_layout(ctx.series)
    if _resolve_xtab_layout(ctx) == "separate":
        # Reuses the horizontal panel renderer — see the comment on
        # `_render_stacked_variable_panels` for why.
        _render_stacked_variable_panels(ctx, cats)
        return
    fig, ax = new_figure(ctx)
    ink, _muted, _grid = chart_furniture(ctx)
    # Stack segments are ordered scale levels → monotonic light→dark gradient.
    clrs = scale_colors(len(segs), chart_accent(ctx))

    # Cross-tab: group the stacked bars by primary classifier (gap + group label), so the
    # SECOND classifier is used instead of a flat undifferentiated row.
    grouped = _grouped_stacked_positions(cats, ctx.series.segment_primary)
    x = np.array([float(p) for p in grouped[0]]) if grouped else np.arange(len(cats))
    flat_vals = [v for seg in segs for v in data[seg] if v is not None]

    # 100%-stacked: every column must reach exactly 100. Normalise each column's
    # segment HEIGHTS to its own total (rounded percentages sum to 99–101) so the
    # tops align, while the data LABELS still show the original percentages. Only
    # where the stack genuinely partitions the column's base — otherwise the true
    # heights are drawn and the axis carries the real maximum (`_stack_scaling`).
    normalise, axis_max = _stack_scaling(ctx.series, cats, segs, data)
    totals = np.array([sum(data[s][i] or 0.0 for s in segs) for i in range(len(cats))])
    norm = (np.where(totals > 0, 100.0 / totals, 1.0) if normalise
            else np.ones(len(cats)))
    # "Too thin to label" — 1% of the value axis unless the author moved it.
    label_min = label_floor(ctx.spec.number_format,
                            default_pct=default_label_floor(ctx.spec.chart_type),
                            axis_max=axis_max)
    col_ink, _col_muted, col_grid = chart_furniture(ctx)
    # A column is drawn thinner when some of its numbers have to sit beside it,
    # so there is a gap between columns for them to sit IN. Placed at the next
    # column's left edge, a number sat on a neighbour it does not describe.
    any_out = any(0.0 < (data[seg][j] or 0.0) * norm[j]
                  for seg in segs for j in range(len(cats)))
    col_w = _STACK_BAR_H_CALLOUT if any_out else _STACK_BAR_H
    # Where the last callout on each column went, so the next clears it.
    last_y: dict[float, float] = {}
    # Measured against the scale the columns are drawn on — the caller sets the
    # limits after this, and against matplotlib's default every label looks as
    # though it fits.
    ax.set_ylim(0, axis_max)
    bottoms = np.zeros(len(cats))

    for i, seg in enumerate(segs):
        orig = np.array([data[seg][j] or 0.0 for j in range(len(cats))])
        heights = orig * norm
        # R4.2: "Not answered" category bars get MUTED grey.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in cats]
        bars = ax.bar(x, heights, bottom=bottoms, label=seg, color=bar_clrs,
                      edgecolor="none", zorder=3, width=col_w)
        for bar, ov, b, h in zip(bars, orig, bottoms, heights):
            if h <= label_min:
                # The author's cut-off: not printed, and not printed beside the
                # column either — a number called out is still on the chart.
                continue
            text = format_value(ov, ctx.series.statistic, ctx.spec.number_format,
                                flat_vals)
            x_mid = bar.get_x() + bar.get_width() / 2
            _w, _h = text_size_in_data(ax, text, fontsize=9.0)
            if h >= _h * 1.15 and bar.get_width() >= _w * 1.06:
                ax.text(
                    x_mid, b + h / 2, text, ha="center", va="center",
                    fontsize=9.0, fontweight="bold",
                    color=contrast_ink(bar.get_facecolor()), zorder=5,
                )
            else:
                # Too short to hold its number: in the gap beside the column, on
                # a line back to the segment it belongs to. Inside the gap, not
                # across it — the far side of a gap belongs to the next column.
                right = bar.get_x() + bar.get_width()
                gap = (1.0 - bar.get_width()) * 0.15
                # The rightmost column has no gap to its right — the plot ends
                # there — so its numbers go to its LEFT instead of off the edge.
                to_left = right + gap + _w > ax.get_xlim()[1]
                side = "right" if to_left else "left"
                at_x = (bar.get_x() - gap) if to_left else (right + gap)
                anchor_x = bar.get_x() if to_left else right
                at_y = b + h / 2
                prev = last_y.get(round(bar.get_x(), 6))
                # Two slivers a couple of percent apart put their numbers a
                # couple of percent apart, which is a few pixels: push the
                # second clear of the first by a line's height.
                if prev is not None and at_y - prev < _h * 1.2:
                    at_y = prev + _h * 1.2
                last_y[round(bar.get_x(), 6)] = at_y
                callout_value(ax, text, at=(at_x, at_y), to=(anchor_x, b + h / 2),
                              ink=col_ink, grid=col_grid, ha=side)
        bottoms = bottoms + heights

    ax.set_xticks(x)
    if grouped:
        # Per-bar tick = the SECONDARY value; the primary is shown once as a group label
        # centred under each group, so both classifiers read clearly.
        ax.set_xticklabels([_secondary_tick(c) for c in cats], fontsize=9.5, color=ink)
        for glabel, gx in grouped[1]:
            ax.text(gx, -0.075, glabel, transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=11.5, fontweight="bold", color=ink)
    else:
        # Wrap + rotate x-axis labels so they are shown in full and never overlap.
        ax.set_xticklabels(
            [_wrap_xtick_label(c) for c in cats], fontsize=10.5, color=ink,
            rotation=_XTICK_ROTATION, ha="right", rotation_mode="anchor",
        )
    # Normalised → the axis IS the 0-100 composition scale, whatever statistic the
    # columns carry. True heights → the axis must read the data's own statistic.
    _apply_column_style(ax, ctx, axis_max, "pct" if normalise else ctx.series.statistic)

    if ctx.spec.elements.legend and len(segs) > 1:
        _legend_below(ax, len(segs), ctx)

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# build_image_bar_stacked
# ---------------------------------------------------------------------------

def text_size_in_data(ax, text: str, *, fontsize: float,
                      weight: str = "bold") -> tuple[float, float]:
    """(width, height) of `text` in the axes' own units."""
    art = ax.text(0, 0, text, fontsize=fontsize, fontweight=weight, alpha=0.0)
    try:
        ax.figure.canvas.draw()
        box = art.get_window_extent(ax.figure.canvas.get_renderer())
        inv = ax.transData.inverted()
        (x0, y0), (x1, y1) = inv.transform([(0, 0), (box.width, box.height)])
        return abs(x1 - x0), abs(y1 - y0)
    finally:
        art.remove()


def text_width_in_data(ax, text: str, *, fontsize: float, weight: str = "bold") -> float:
    """How wide `text` would be, in the axes' own x units.

    "Too small to hold its number" is a question about the NUMBER, not about a
    percentage of the axis: "2 %" needs the same room whatever the chart is
    scaled to, and a fixed cut-off either drops values that would have fitted or
    prints ones that collide with their neighbour — which is what a reader saw
    as a smear of digits at the foot of a scale.
    """
    art = ax.text(0, 0, text, fontsize=fontsize, fontweight=weight, alpha=0.0)
    try:
        ax.figure.canvas.draw()
        box = art.get_window_extent(ax.figure.canvas.get_renderer())
        x0, x1 = ax.transData.inverted().transform([(0, 0), (box.width, 0)])[:, 0]
        return abs(x1 - x0)
    finally:
        art.remove()


#: A stacked bar's row is drawn thinner when some of its numbers have to sit
#: outside it, so there is a gap for them to sit in. Only then: a chart whose
#: every segment holds its own number keeps the fuller bar.
_STACK_BAR_H: float = 0.8
_STACK_BAR_H_CALLOUT: float = 0.62
#: How far a called-out number sits from the bar's edge, and the least two of
#: them may be apart along the bar — the slivers of a scale sit together, and
#: their numbers would land on each other.
#:
#: Kept well inside the gap between rows: at the midpoint a number is as near
#: the bar above it as the one it belongs to, and the eye goes to the nearer.
_CALLOUT_OFFSET: float = 0.14
_CALLOUT_MIN_GAP_FRAC: float = 0.055


def callout_value(ax, text: str, *, at, to, ink: str, grid: str,
                  ha: str = "center", va: str = "center") -> None:
    """One number that would not fit inside its own piece, drawn beside it.

    `at` is where the text goes, `to` the point on the piece it describes. The
    line between them is the whole point: without it a number floating near a
    stack of slivers belongs to any of them.
    """
    ax.annotate(text, xy=to, xytext=at, ha=ha, va=va, fontsize=8.5,
                fontweight="bold", color=ink, annotation_clip=False, zorder=6,
                arrowprops=dict(arrowstyle="-", color=grid, linewidth=0.9,
                                shrinkA=1, shrinkB=1))


def final_axis_max(ctx, axis_max: float) -> float:
    """The x limit the finished panel carries, not the one it is drawn with.

    Labels are placed before `_apply_bar_style` and `_draw_row_summary` run, and
    the row-summary column widens the axis by ~18% to make room for its strip.
    Measuring a label against the narrower scale says it fits when it will be
    drawn into a segment about 15% narrower than measured — the failure the
    measurement exists to prevent.
    """
    vals = _row_summary_by_bar(ctx.series, getattr(ctx.series, "segments", ()))
    if vals and not all(v is None for v in vals):
        return 118.0 * axis_max / 100.0
    return axis_max


def spread_along(targets: list[float], room: list[float], limit: float,
                 pad: float) -> list[float]:
    """Where to put numbers that all point at nearly the same place.

    Each wants to sit at its target; each needs `room` of its own. Walking
    right by a fixed step was the old rule, and a fixed step is exactly what
    the measurement above exists to avoid — on a narrow chart the step was
    smaller than the numbers, so they overlapped anyway, and with several
    slivers in a row the walk marched them off the end of the plot.

    So: place left to right, never closer than the two halves plus a pad, then
    if the run has overflowed `limit`, push the whole run back left — moving
    them together keeps each one nearer its own target than shuffling would.
    """
    out: list[float] = []
    for i, want in enumerate(targets):
        x = want
        if out:
            x = max(x, out[-1] + room[i - 1] / 2 + room[i] / 2 + pad)
        out.append(x)
    over = (out[-1] + room[-1] / 2) - limit if out else 0.0
    if over > 0:
        out = [x - over for x in out]
    return out


def _draw_stacked_panel(ax, bars, stack, data, clrs, ctx, y, flat_vals, *,
                        normalise: bool = True, axis_max: float = 100.0) -> None:
    """Draw ONE stacked horizontal panel onto `ax`.

    Shared by the single-axes builder and the SEPARATE panel renderer — so both
    get the same honesty treatment.

    `normalise` (decided per chart by `_stack_scaling`): when True each bar's
    segment WIDTHS are scaled to its own total so the right edges align at 100,
    while the LABELS keep the original rounded percentages (spec 2026-08-04) —
    the 100%-stacked reading. When False the TRUE widths are drawn against an
    axis reaching `axis_max`, because the segments overlap and do not partition
    the bar (see `_stack_scaling`)."""
    n_bars = len(bars)
    totals = np.array([sum(data[s][i] or 0.0 for s in stack) for i in range(n_bars)])
    if normalise:
        norm = np.where(totals > 0, 100.0 / totals, 1.0)
    else:
        norm = np.ones(n_bars)
    # "Too thin to label" is a share of the value axis, not a fixed 1 unit: on a
    # true-width 0-465 axis a 1-unit sliver is invisible but would still be
    # labelled, and the labels would pile up on each other. 1% by default, and
    # the author's own cut-off when they set one — a 100%-stacked scale puts its
    # whole tail into slivers narrower than the numbers that belong in them.
    label_min = label_floor(ctx.spec.number_format,
                            default_pct=default_label_floor(ctx.spec.chart_type),
                            axis_max=axis_max)
    # A number that does not fit inside its own segment is drawn BESIDE the bar
    # on a line back to it, rather than dropped — the tail of a scale is exactly
    # where a reader of the finished deck cannot look the number up.
    ink, _muted, grid = chart_furniture(ctx)
    # What each cell would say, and whether its own segment can hold it. The
    # author's cut-off still applies — a segment under it is called out however
    # well the number would have fitted — but the DEFAULT test is the honest
    # one: measure the number.
    said = {(seg, j): format_value(data[seg][j] or 0.0, ctx.series.statistic,
                                   ctx.spec.number_format, flat_vals)
            for seg in stack for j in range(n_bars)}
    # Measured against the scale the bars are actually drawn on. The caller
    # applies the x limits AFTER this, so without pinning them here every
    # measurement is taken against matplotlib's default 0..1 and every label
    # looks as though it fits — which is how a row of digits came to be printed
    # on top of each other at the foot of a scale.
    ax.set_xlim(0, final_axis_max(ctx, axis_max))
    room = {t: text_width_in_data(ax, t, fontsize=9.0) * 1.06 for t in set(said.values())}

    def _width(seg, j) -> float:
        return (data[seg][j] or 0.0) * norm[j]

    def _fits(seg, j) -> bool:
        return _width(seg, j) >= room[said[(seg, j)]]

    def _hidden(seg, j) -> bool:
        """Under the author's cut-off. They said not to print it, so it is not
        printed anywhere — a number called out beside the chart is still on the
        chart."""
        return _width(seg, j) <= label_min

    any_callout = any(
        _width(seg, j) > 0 and not _hidden(seg, j) and not _fits(seg, j)
        for seg in stack for j in range(n_bars))
    bar_h = _STACK_BAR_H_CALLOUT if any_callout else _STACK_BAR_H
    # The callouts per bar, gathered as the stack is walked and laid out in one
    # pass at the end: where each goes depends on its neighbours, which are not
    # known until the whole row has been seen.
    pending: dict[float, list[tuple[float, float, str]]] = {}
    lefts = np.zeros(n_bars)
    for i, seg in enumerate(stack):
        orig = np.array([data[seg][j] or 0.0 for j in range(n_bars)])
        widths = orig * norm
        # R4.2: "Not answered" category bars get MUTED grey.
        bar_clrs = [MUTED if c == NOT_ANSWERED_LABEL else clrs[i] for c in bars]
        ax.barh(y, widths, left=lefts, label=seg, color=bar_clrs, height=bar_h,
                edgecolor="none", zorder=3)
        for j, (yi, ov, l, w, bc) in enumerate(zip(y, orig, lefts, widths, bar_clrs)):
            text = said[(seg, j)]
            if _hidden(seg, j):
                pass                       # the author's cut-off: nothing at all
            elif _fits(seg, j):
                ax.text(l + w / 2, yi, text,
                        ha="center", va="center", fontsize=9.0, fontweight="bold",
                        color=contrast_ink(bc), zorder=5)
            elif w > 0:
                pending.setdefault(float(yi), []).append((l + w / 2, w, text))
        lefts = lefts + widths

    # ABOVE its own bar, never below: the gap under a bar belongs to the next
    # one down, and a number sitting in it reads as that bar's however
    # carefully the line is drawn.
    limit = final_axis_max(ctx, axis_max)
    for yi, items in pending.items():
        items.sort()
        widths_needed = [room[t] for _x, _w, t in items]
        placed = spread_along([x for x, _w, _t in items], widths_needed,
                              limit, room[items[0][2]] * 0.25)
        for (target, _w, text), at_x in zip(items, placed):
            callout_value(ax, text, at=(at_x, yi + bar_h / 2 + _CALLOUT_OFFSET),
                          to=(target, yi + bar_h / 2), ink=ink, grid=grid,
                          va="bottom")


def build_image_bar_stacked(ctx) -> None:
    """Stacked horizontal bar chart: bars = classifier segments, stack = answer
    categories (house style). Normalised to 100% per bar where the stack really
    partitions the bar's base, otherwise drawn at true widths (`_stack_scaling`)."""
    cats, segs, data = _stacked_layout(ctx.series)
    if _resolve_xtab_layout(ctx) == "separate":
        _render_stacked_variable_panels(ctx, cats)
        return
    fig, ax = new_figure(ctx)
    ink, _muted, _grid = chart_furniture(ctx)
    # Stack segments are ordered scale levels → monotonic light→dark gradient.
    clrs = scale_colors(len(segs), chart_accent(ctx))

    n_cats = len(cats)
    # Cross-tab: group the stacked bars by primary classifier (gap + group label).
    grouped = _grouped_stacked_positions(cats, ctx.series.segment_primary)
    if grouped:
        maxp = max(grouped[0])
        y = np.array([maxp - p for p in grouped[0]])   # first cat at top
    else:
        y = np.arange(n_cats)[::-1]
    flat_vals = [v for seg in segs for v in data[seg] if v is not None]

    normalise, axis_max = _stack_scaling(ctx.series, cats, segs, data)
    _draw_stacked_panel(ax, cats, segs, data, clrs, ctx, y, flat_vals,
                        normalise=normalise, axis_max=axis_max)

    ax.set_yticks(y)
    if grouped:
        # Per-bar tick = the SECONDARY value; the primary is a group label to the left.
        ax.set_yticklabels([_secondary_tick(c) for c in cats], fontsize=10.5, color=ink)
        for glabel, gpos in grouped[1]:
            ax.text(-0.13, maxp - gpos, glabel, transform=ax.get_yaxis_transform(),
                    ha="center", va="center", rotation=90,
                    fontsize=11.5, fontweight="bold", color=ink)
    else:
        # Wrap long y-axis labels onto as many lines as needed (full text, no '…').
        ax.set_yticklabels([_wrap_label(c) for c in cats], fontsize=11.5, color=ink)
    ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
    # Normalised → the axis IS the 0-100 composition scale, whatever statistic the
    # bars carry. True widths → the axis must read the data's own statistic.
    _apply_bar_style(ax, ctx, axis_max, "pct" if normalise else ctx.series.statistic)
    # right-hand per-row column (if configured), against the axis just applied
    _draw_row_summary(ctx, ax, y, cats, ax.get_xlim()[1])

    if ctx.spec.elements.legend and len(segs) > 1:
        _legend_below(ax, len(segs), ctx)

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# Shared legend styler (thin wrapper around the shared helper in _mpl)
# ---------------------------------------------------------------------------

def _style_legend(ax, ctx, loc: str = "best") -> None:
    """Apply house-style formatting to an axes legend."""
    style_legend(ax, ctx, loc)
