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
import textwrap

from reportbuilder.render.shape import ADDITIVE_STATISTICS
from reportbuilder.render.image.label_fit import register_category_labels

import numpy as np
from reportbuilder.render.image._mpl import (apply_axis_titles, chart_accent,
    chart_furniture, new_figure, new_tall_figure, new_figure_grid, render_png, place_picture,
    series_label, with_base, place_total, colours_by_series, coded_order,
    place_picture_square, series_values, format_value, label_floor, default_label_floor,
    author_label_floor, style_legend,
    fit_panel_titles, force_break_token, separate_panel_rows,
    wrap_label, wrap_label_capped,
    VALUE_GID,
    _new_agg_figure, _EMU_PER_IN, wants_group_base, _value_axis,
)
from reportbuilder.render.base import note
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
    # The strip is FURNITURE, not data. Anything that centres itself on this
    # chart — the legend below it — must centre on the bars, so record where the
    # bars actually end. Without it the legend anchored at axes x=0.5, which is
    # 59 % of the way across the data, and sat visibly right of what it names.
    # (Johan, 2026-09-17)
    ax._nsight_content_xmax = axis_max
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


#: Statistics whose chart is ONE value per group rather than a distribution —
#: `stats.registry` calls them the "summary" family, and `_summary` is the
#: builder they route to. Named here rather than imported so the renderer keeps
#: no dependency on the stats registry; `test_single_category_tick` pins the two
#: lists together.
_SUMMARY_STATISTICS = frozenset({"mean", "median", "sum"})


def _category_ticks(cats, wrap, statistic: str = "") -> list[str]:
    """The category axis labels — blank for a lone SUMMARY category.

    `_summary` builds one category × segments, and that category is the question
    itself (`question.text or var.label`). Its bars are the classifier's groups,
    named in the legend, so the tick stands under every one of them, tells none
    apart, and repeats the question the subtitle already carries — printed
    rotated under the axis where it reads as an axis title nobody asked for.
    (Reported 2026-09-08: "vaaka-akselille tulee otsikko vaikka ei pitäisi"; the
    axis-title field was empty, and this was never an axis title.)

    The statistic is what separates that from a DISTRIBUTION that happens to
    have one category left — a question whose other options were empty and
    hidden. There the lone category is an ANSWER ("Attendo"), the subtitle is
    the question ("Mitä merkkiä käytät?"), and blanking the tick would leave an
    unnamed bar. It keeps its label. (Johan, 2026-09-08)
    """
    if len(cats) <= 1 and statistic in _SUMMARY_STATISTICS:
        return [""]
    return [wrap(c) for c in cats]


def _wrap_xtick_label(text: str) -> str:
    """Wrap a vertical-bar x-axis label (narrower wrap; rotation handles the rest)."""
    return _wrap_label(text, width=_XLABEL_WRAP_WIDTH)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _tick_text(v: float) -> str:
    """Integer-looking tick → no decimals; otherwise trim trailing zeros."""
    return str(int(v)) if float(v).is_integer() else f"{v:g}"


# Up to this many series, a below-the-plot legend is compact enough; beyond it a
# right-side vertical legend keeps the plot large (uses the spare horizontal space).
_LEGEND_BELOW_MAX: int = 5


#: Point size a column's value label is drawn at, and the smallest it may shrink
#: to before turning on its side. Below ~7pt a number on a slide is decoration.
_VALUE_LABEL_PT: float = 9.5
_VALUE_LABEL_MIN_PT: float = 7.5


def _value_label_layout(fig, ax, n_cats: int, bar_w: float,
                        widest: str) -> tuple[float, float] | None:
    """(fontsize, rotation) for a column's value label, or None if it cannot fit.

    Replaces a bare segment count. A count cannot tell a roomy chart from a
    cramped one — the same five groups are comfortable on a wide slide with
    three categories and hopeless on a narrow one with twelve — so it dropped
    every number on a chart that had room for them all. Reported as "vertical
    bar chartissa ei näy prosenttilukuja kun tarkastelee lukuja eri
    taustaryhmissä". (Johan, 2026-09-10)

    Three answers, in the order a person would try them: draw it flat if it
    fits; turn it on its side if the column is too narrow but the number is
    short enough to stand up in it; give up when neither works, because a wall
    of overlapping text is worse than the grid and the legend alone.
    """
    # The room a label has is the spacing between ADJACENT bars, which is the
    # bar's own width — not the plot divided by the bar count. Bars fill 0.7 of
    # a category slot and the rest is the gap between categories, so dividing
    # by the count over-states the room by about 40% and lets numbers overlap
    # while the arithmetic says they fit. `bar_w` is in data units and one
    # category slot is 1, so this converts exactly, and it is right for the
    # cross-tab layout too, where the widths differ.
    plot_w_in = ax.get_position().width * fig.get_size_inches()[0]
    per_bar_in = bar_w * plot_w_in / max(n_cats, 1)
    for pt in (_VALUE_LABEL_PT, _VALUE_LABEL_MIN_PT):
        if _measure_max_label_width_in([widest], pt) <= per_bar_in * 0.92:
            return pt, 0.0
    # On its side the number needs only its LINE HEIGHT across the column.
    if (_VALUE_LABEL_MIN_PT / 72.0) * 1.35 <= per_bar_in:
        return _VALUE_LABEL_MIN_PT, 90.0
    return None


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


#: How far below the plot the legend row sits, as a share of the axes height.
#: Was 0.08, which left about 7pt between an x-axis TITLE and the legend — the
#: two read as one crowded block. ("Maybe add a bit space between the legend and
#: the chart data", 2026-09-16)
_LEGEND_GAP: float = 0.13
#: And further when an axis title has to fit in that space.
_LEGEND_GAP_WITH_AXIS_TITLE: float = 0.20


def _legend_below(ax, n_segs: int, ctx, y: float | None = None) -> None:
    """Place a chart's legend in a horizontal row BELOW the plot (an in-axes legend
    would cover the bars). `y` is the bbox anchor offset — push it lower for charts
    with rotated x-axis tick labels (clustered vertical bars) so it clears them.
    bbox_inches='tight' expands the figure to include it.

    `None` picks the gap from what is actually in that space: an x-axis title
    needs room of its own, and a caller that names a `y` still gets exactly it.
    """
    if y is None:
        has_axis_title = bool((getattr(ctx.spec, "axis_x_title", "") or "").strip())
        y = -(_LEGEND_GAP_WITH_AXIS_TITLE if has_axis_title else _LEGEND_GAP)
    handles, labels = ax.get_legend_handles_labels()
    # The legend draws its labels exactly as they are: what Category labels
    # lists is what the slide says.
    #
    # It used to cut a numeric rating scale ("1 - Erittäin huono", "2", …
    # "7 - Erittäin hyvä") to bare 1…7 and move the endpoint words to a
    # caption at the foot. The editor went on listing the words, so the slide
    # and its settings disagreed, and retyping a label did nothing because a
    # label equal to the data's own is not stored: "Category labels määritys
    # ei siirry oikein legendiin". Every exception it grew — the series
    # legend's age bands, Prima Pet's money bands, an authored rename — was
    # the shortener throwing away words somebody needed. (Johan, 2026-09-23)
    #
    # Does the row FIT? Measured, not counted.
    #
    # This was a count (`n_segs <= 5`, seven for a shortened scale), so six short
    # words went onto two rows across the full width of a slide with room for
    # all six, and a count could never tell that from six long ones that do not
    # fit. `_value_label_layout` already carries this lesson about value labels:
    # "A count cannot tell a roomy chart from a cramped one."
    #
    # The handle, its gap and the space between entries are the legend's own
    # keyword values below, converted from points to inches so they are measured
    # in the units the text is. A tenth of an inch of slack keeps a row that only
    # just fits off the very edge. (Johan, 2026-09-16)
    _LEGEND_FS = 9.5
    entry_in = (1.1 + 0.5 + 1.2) * _LEGEND_FS / 72.0      # handle + pad + gap
    widths = [_measure_max_label_width_in([l], _LEGEND_FS) for l in labels]
    # Centred on the CHART, not on the axes. They are the same thing until
    # something reserves part of the axes for furniture — the row-summary column
    # does, by 18 % — see `_draw_row_summary`.
    span = ax.get_xlim()[1] or 1.0
    content = getattr(ax, "_nsight_content_xmax", None)
    centre = (content / span) / 2 if content else 0.5
    # The room is what lies either side of that centre, not the figure's whole
    # width: the plot sits right of middle behind its group labels, so a row
    # that fits the figure can still run off its right edge. Nothing found this
    # while a numbered scale was cut to 1…7; a worded one drawn in full in a
    # half-width slot did.
    fig_w_in = ax.get_figure().get_size_inches()[0]
    box = ax.get_position()
    centre_in = (box.x0 + centre * box.width) * fig_w_in
    room_in = 2 * min(centre_in, fig_w_in - centre_in) - 0.1

    def row_in(ncol: int) -> float:
        # Reading order is row-major, so column k holds entries k, k+ncol, …
        return sum(max(widths[k::ncol]) for k in range(ncol)) + entry_in * ncol

    ncol = next((c for c in range(n_segs, 0, -1) if row_in(c) <= room_in), 1)
    if ncol < n_segs:
        handles, labels = _rowmajor_legend(handles, labels, ncol)
    leg = ax.legend(
        handles, labels,
        loc="upper center", bbox_to_anchor=(centre, y),
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


def _total_position(ctx) -> str:
    """The author's "Total position": "top", "bottom" or "auto" (as always)."""
    return getattr(ctx.spec, "total_position", "auto") or "auto"


def _place_total_category(cats, data, position: str):
    """`place_total` for a chart whose Total is a CATEGORY — a summary chart of
    groups, transposed so the groups are what the axis names. The values move
    with their names."""
    order = place_total(cats, position)
    if order == list(cats):
        return cats, data
    idx = [list(cats).index(c) for c in order]
    return order, {s: [vals[i] for i in idx] for s, vals in data.items()}


def _group_name(series, seg: str, *, show_base: bool = True) -> str:
    """A group named where it stands for itself — a bar, a panel's legend entry —
    with the number of people in it: "Naiset (n=501)".

    `show_base` off drops the number and keeps the name — `elements.group_base`.
    """
    if not show_base:
        return _secondary_tick(seg)
    return with_base(_secondary_tick(seg), series.base_n.get(seg))


def _bar_names(series, bars, *, short: bool, show_base: bool = True) -> list[str]:
    """The names a stacked chart's bars are drawn with.

    "Kohderyhmäkohtaiset n-luvut tulevat esille vertical ja horizontal bar
    kaaviotyypeissä, mutta ei stacked kaavioissa." A grouped bar says its base in
    the legend, because there the series are the groups. A stacked bar's legend
    is the answer scale, so it says it on the bars, which are. Only where the
    bars ARE groups: a battery's statements are not, and neither is the single
    bar of everyone, whose N the slide already prints. (Johan, 2026-09-11)

    `short` names a cross-tab's bars by their second group only, the first
    being printed once beside them."""
    # A chart of ONE bar called "Total" is everybody, and saying so under the
    # axis tells the reader nothing they cannot see. On a vertical stack it also
    # crowded the x-axis title and the legend into one strip. Blank rather than
    # dropped, so the bar keeps its position on the axis.
    #
    # Only when it is alone: beside real groups, "Total" is what distinguishes
    # the reference bar from them. And only for "Total" — a lone category in a
    # distribution is otherwise a real answer ("Attendo"), which `_category_ticks`
    # makes the same distinction about. (Johan, 2026-09-16)
    if len(bars) == 1 and str(bars[0]).strip() == "Total":
        return [""]
    name = _secondary_tick if short else (lambda b: b)
    # `show_base` off is the author declining the number (`elements.group_base`);
    # the other two are the chart having no group to state one for.
    if (not show_base
            or not getattr(series, "segments_are_groups", True)
            or all("Total" in b for b in bars)):
        return [name(b) for b in bars]
    return [with_base(name(b), series.base_n.get(b)) for b in bars]


# ---------------------------------------------------------------------------
# The primary group's label beside (or under) its rows
# ---------------------------------------------------------------------------
#
# A cross-tab's "Suomi" stands rotated beside its rows. A split battery's
# primary is a whole statement — up to 241 characters on a customer's slide —
# and rotated it smears; left out, every bar carried "<statement> · <group>" and
# was cut to its first words with the group lost. So a label too long to stand
# rotated is written out horizontally, wrapped into a column of its own beside
# its rows (under its columns on a vertical chart), and the rows are named by
# their group alone. A label that fits is drawn exactly as it always was.
# (Johan, 2026-09-11)

#: Marks a drawn primary-group label so later passes can find it.
_GROUP_GID = "nsight-group"
_GROUP_FS: float = 11.5
#: A written-out group label starts at this size and is never set below the floor.
_GROUP_BLOCK_FS: float = 10.0
_GROUP_BLOCK_MIN_FS: float = 7.5
#: The column a written-out label may take beside its rows: this share of the
#: figure, and never wider than this — past it the bars lose more than the
#: reader gains.
_GROUP_BLOCK_COL_FRAC: float = 0.28
_GROUP_BLOCK_COL_IN: float = 3.4
#: Lines a written-out label may take under its columns.
_GROUP_UNDER_MAX_LINES: int = 5


def _group_sizes(cats, segment_primary) -> dict[str, int]:
    """How many bars each primary group holds."""
    sizes: dict[str, int] = {}
    for c in cats:
        g = (segment_primary or {}).get(c, c)
        sizes[g] = sizes.get(g, 0) + 1
    return sizes


def _text_extent_px(fig, text: str, fontsize: float, weight: str = "normal") -> tuple[float, float]:
    """(width, height) in px of `text` as this figure will draw it — in the
    template's face when it has one, since that is the face it is saved in."""
    kw = {"fontsize": fontsize, "fontweight": weight}
    family = getattr(fig, "_nsight_chart_font", "")
    if family:
        kw["fontfamily"] = family
    art = fig.text(0, 0, text, **kw)
    try:
        box = art.get_window_extent(fig.canvas.get_renderer())
        return box.width, box.height
    finally:
        art.remove()


def _wrap_into(fig, text: str, width_px: float, height_px: float, *,
               max_lines: int | None = None,
               only_size: float | None = None) -> tuple[str, float]:
    """`text` wrapped to fit a `width_px` × `height_px` box: (wrapped text, size).

    The largest size first, a step smaller at a time down to the floor; the full
    text whenever it fits at all, and only at the floor as many lines as there
    is room for, with an ellipsis.

    `only_size` fixes the size instead of searching for one, so a block of
    labels can be set at the one size that suits the worst of them rather than
    each finding its own — which put 7.5pt beside 10pt in a single column.
    """
    flat = " ".join(text.split())
    if only_size is not None:
        sizes = [only_size]
    else:
        sizes = [_GROUP_BLOCK_FS]
        while sizes[-1] * 0.9 >= _GROUP_BLOCK_MIN_FS:
            sizes.append(sizes[-1] * 0.9)
        if sizes[-1] > _GROUP_BLOCK_MIN_FS:
            sizes.append(_GROUP_BLOCK_MIN_FS)
    for fs in sizes:
        line_px = fs * 1.25 * fig.dpi / 72.0
        allowed = max(1, int(height_px // line_px))
        if max_lines:
            allowed = min(allowed, max_lines)
        per_char = _text_extent_px(fig, flat, fs)[0] / max(len(flat), 1)
        chars = max(8, int(width_px / max(per_char, 0.1)))
        wrapped = wrap_label(flat, chars)
        # Characters only estimate width: measure, and narrow until it fits.
        while _text_extent_px(fig, wrapped, fs)[0] > width_px and chars > 8:
            chars = int(chars * 0.92)
            wrapped = wrap_label(flat, chars)
        if wrapped.count("\n") + 1 <= allowed:
            return wrapped, fs
        if fs == sizes[-1]:
            return wrap_label_capped(flat, chars, allowed), fs
    return flat, sizes[-1]                                   # pragma: no cover


def _plan_group_labels_beside(fig, labels, sizes, pitch_px):
    """("rotated", {}, 0) when every group name fits along its rows, as it always
    has; else ("written", {name: (wrapped, size)}, column width in inches)."""
    if all(_text_extent_px(fig, g, _GROUP_FS, "bold")[0] <= sizes.get(g, 1) * pitch_px
           for g, _pos in labels):
        return "rotated", {}, 0.0
    fig_w_in = fig.get_size_inches()[0]
    col_px = min(_GROUP_BLOCK_COL_IN, _GROUP_BLOCK_COL_FRAC * fig_w_in) * fig.dpi
    # One size for the whole block, not one per statement. Sized alone, a long
    # statement dropped to the 7.5pt floor beside a neighbour still at 10pt —
    # a 25% step down one column, which is what made the block look ragged.
    # The smallest any of them needs is the size they all take.
    first = {g: _wrap_into(fig, g, col_px, sizes.get(g, 1) * pitch_px)
             for g, _pos in labels}
    one_size = min(fs for _text, fs in first.values())
    blocks = {g: (_wrap_into(fig, g, col_px, sizes.get(g, 1) * pitch_px,
                             only_size=one_size)[0], one_size)
              for g, _pos in labels}
    width_in = max(_text_extent_px(fig, t, fs)[0] for t, fs in blocks.values()) / fig.dpi
    return "written", blocks, width_in


def _draw_group_labels_under(fig, ax, labels, sizes, ink, *,
                             names_depth_px: float | None = None) -> None:
    """A vertical chart's primary group names, centred under their columns.

    A name that fits its columns is drawn as it always was. One that does not is
    wrapped to its columns' width and set below the row names — which may take
    two lines — so it can neither run into its neighbour nor into them.

    `names_depth_px` is how far ROTATED row names reach below the axis; given,
    every group name is set below that band instead of at the fixed offset a
    flat row of names leaves room for."""
    x0, x1 = ax.get_xlim()
    pitch_px = ax.bbox.width / max(abs(x1 - x0), 1e-6)
    h = max(ax.bbox.height, 1.0)
    if names_depth_px is None:
        top_fit = -0.075
        top_written = -((2 * 9.5 * 1.25 + 8.0) * fig.dpi / 72.0) / h
    else:
        top_fit = top_written = -(names_depth_px + 4.0 * fig.dpi / 72.0) / h
    if all(_text_extent_px(fig, g, _GROUP_FS, "bold")[0] <= sizes.get(g, 1) * pitch_px
           for g, _gx in labels):
        for glabel, gx in labels:
            ax.text(gx, top_fit, glabel, transform=ax.get_xaxis_transform(),
                    ha="center", va="top", fontsize=_GROUP_FS, fontweight="bold",
                    color=ink, gid=_GROUP_GID)
        return
    top = top_written
    # One size for every group name, for the same reason as the beside layout.
    one_size = min(
        _wrap_into(fig, g, sizes.get(g, 1) * pitch_px * 0.94, 1e9,
                   max_lines=_GROUP_UNDER_MAX_LINES)[1]
        for g, _gx in labels)
    for glabel, gx in labels:
        wrapped, fs = _wrap_into(fig, glabel, sizes.get(glabel, 1) * pitch_px * 0.94,
                                 1e9, max_lines=_GROUP_UNDER_MAX_LINES,
                                 only_size=one_size)
        ax.text(gx, top, wrapped, transform=ax.get_xaxis_transform(), ha="center",
                va="top", multialignment="center", fontsize=fs, color=ink,
                gid=_GROUP_GID)


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
    # Separate panels are one per classifying VARIABLE, so they need two. A split
    # battery is grouped too (by statement), and "Separate panels" left in its
    # options from a second variable since removed must not start drawing one
    # panel per statement. (2026-09-11)
    if mode == "separate" and not getattr(ctx.spec, "classifying_var_2", None):
        mode = "auto"
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


def _panel_legends(fig, legends, *, max_ncol: int, fontsize: float = 9.0) -> None:
    """Give every panel its legend, each no wider than its own panel.

    `legends` is [(axes, handles, names)]. A panel's legend is its own — one
    group is 240 people in one panel and 261 in the next — but it was set in as
    many as four columns whatever the panel's width, and entries like
    "Pääkaupunkiseudulla (n=118)" made each legend wider than its panel: side by
    side, every legend was printed through its neighbours'. Fewer columns first,
    then smaller type down to the names' own floor. Call once the panels are laid
    out (`subplots_adjust`), since that is the width being fitted to.
    (visual QA, 2026-09-19)
    """
    from reportbuilder.render.image.label_fit import _MIN_PT

    r = fig.canvas.get_renderer()
    sizes = [fontsize]
    while sizes[-1] * 0.9 >= _MIN_PT:
        sizes.append(sizes[-1] * 0.9)
    for ax, handles, names in legends:
        # The panel plus its half of the gutter on each side is the room there is.
        others = [a.bbox for a in fig.axes if a is not ax and a.get_visible()]
        right = min((b.x0 for b in others if b.x0 >= ax.bbox.x1), default=fig.bbox.x1)
        left = max((b.x1 for b in others if b.x1 <= ax.bbox.x0), default=fig.bbox.x0)
        limit = min(ax.bbox.x0 - left, right - ax.bbox.x1) + ax.bbox.width
        leg = None
        for fs in sizes:
            for ncol in range(min(len(names), max_ncol), 0, -1):
                if leg is not None:
                    leg.remove()
                leg = ax.legend(*_rowmajor_legend(handles, names, ncol),
                                loc="upper center",
                                bbox_to_anchor=(0.5, -0.12), ncol=ncol,
                                frameon=False, fontsize=fs)
                if leg.get_window_extent(r).width <= limit:
                    break
            else:
                continue
            break


def _label_panel_bars(fig, ctx, drawn, *, vertical: bool, n_cat: int,
                      all_vals, max_val: float, ink) -> None:
    """Value labels for a chart of several panels, by the same rules as one.

    `drawn` is [(ax, positions, values, thickness)] — one entry per series in
    each panel. The panel layouts drew their bars and nothing else, so a
    vertical bar split by TWO classifying variables showed no numbers at all,
    percent or count alike: "Kun vertical barissa laittaa 2 luokittelevaa
    muuttujaa, niin palkkien numeroarvot katoavat kuvasta." (2026-09-24)

    Called once the panels are laid out, because the room a number has is the
    width of a bar as drawn. Columns are measured once for the whole chart
    against the widest number and the narrowest bar — flat, then on their side,
    then none — so every column is labelled the same way or none is, exactly as
    `_render_column_v` does. Bars on their side take the rule of
    `_render_bar_h`: a number sized to the bar's thickness, at its end.
    """
    if not drawn or not all_vals:
        return
    off = _label_offset(max_val)
    _floor = author_label_floor(ctx.spec, ctx.series.statistic, all_vals)

    def text(v):
        return format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals)

    if vertical:
        widest = max((text(v) for v in all_vals), key=len, default="")
        narrowest = min(drawn, key=lambda d: d[3])
        fit = _value_label_layout(fig, narrowest[0], n_cat, narrowest[3], widest)
        if not fit:
            note(ctx, "unlabelled", n_cat)
            return
        pt, rot = fit
        for ax, xs, vals, _w in drawn:
            for xi, v in zip(xs, vals):
                if v is not None and v >= _floor:
                    ax.text(xi, v + off, text(v), ha="center", va="bottom", rotation=rot,
                            fontsize=pt, fontweight="bold", color=ink, zorder=5,
                            gid=VALUE_GID)
        return
    ax0, _ys, _vals, h0 = min(drawn, key=lambda d: d[3])
    per_bar_pt = (ax0.get_position().height * fig.get_size_inches()[1] * 72.0
                  / max(n_cat, 1) * h0)
    if per_bar_pt < _MIN_LABEL_BAR_PT:
        note(ctx, "unlabelled", n_cat)
        return
    value_fs = max(5.5, min(9.5, per_bar_pt * 0.9))
    # A number at the end of the longest bar needs room INSIDE its panel: the
    # axis ends at that bar, and the next panel starts right after the gutter —
    # "80 %" ran into the neighbour's axis. The axis is lengthened by exactly the
    # widest number, so the ticks stay where they were.
    widest = max((text(v) for v in all_vals), key=len, default="")
    label_in = _measure_max_label_width_in([widest], value_fs) + 0.04
    panel_in = ax0.get_position().width * fig.get_size_inches()[0]
    if label_in >= 0.5 * panel_in:
        note(ctx, "unlabelled", n_cat)
        return
    for ax in {id(d[0]): d[0] for d in drawn}.values():
        lo, hi = ax.get_xlim()
        need = lo + (max_val + off - lo) / (1.0 - label_in / panel_in)
        if need > hi:
            ax.set_xlim(lo, need)
    for ax, ys, vals, _h in drawn:
        for yi, v in zip(ys, vals):
            if v is not None and v >= _floor:
                ax.text(v + off, yi, text(v), va="center", ha="left",
                        fontsize=value_fs, fontweight="bold", color=ink, zorder=5,
                        gid=VALUE_GID)


def _thin_panel_ticks(fig, axes) -> None:
    """Keep the value axes' numbers of side-by-side panels from running together.

    On narrow horizontal panels one panel's last number met the next panel's
    first — "150" and "0" read as "1500" — and within a panel "0 50 100 150"
    touched as well. Once laid out, the numbers are measured; while any two
    touch, every other one is dropped on every panel alike (the first stays, so
    each axis still starts at its zero), down to two. The gridlines keep their
    places: only the numbers thin.
    """
    axes = [ax for ax in axes if ax.get_visible()]
    if not axes:
        return
    r = fig.canvas.get_renderer()
    for _ in range(4):
        fig.draw_without_rendering()
        boxes = sorted((t.get_window_extent(r) for ax in axes
                        for t in ax.get_xticklabels() if t.get_visible() and t.get_text()),
                       key=lambda b: b.x0)
        touching = any(a.x1 + 2 > b.x0 and a.y1 > b.y0 and b.y1 > a.y0
                       for a, b in zip(boxes, boxes[1:]))
        if not touching:
            return
        for ax in axes:
            ticks = list(ax.get_xticks())
            names = [t.get_text() for t in ax.get_xticklabels()]
            shown = [i for i, n in enumerate(names) if n]
            if len(shown) <= 2:
                return
            keep = set(shown[::2])
            ax.set_xticks(ticks, [n if i in keep else "" for i, n in enumerate(names)])


def _render_small_multiples(ctx, cats, *, vertical: bool) -> None:
    """Cross-tab SMALL MULTIPLES: one subplot per PRIMARY value, each a clustered bar of
    (answer categories × the SECONDARY classifier). Shared value axis + one legend."""
    from matplotlib.patches import Patch
    series = ctx.series
    groups = _primary_groups(series)
    _c, _s, data = series_values(series)
    n_cat = len(cats)
    n_sec = max((len(segs) for _p, segs in groups), default=1)
    ramp = series_colors(n_sec, palette=template_palette(ctx),
                         accent=chart_accent(ctx))

    def panel_colours(segs):
        # Keyed by position in the CODED order, the same in every panel, so a
        # group reversed by Survey order Descending keeps its colour.
        return colours_by_series(ramp[:len(segs)], coded_order(series, segs), segs)
    all_vals = [v for _p, segs in groups for s in segs for v in data.get(s, []) if v is not None]
    max_val = max(all_vals, default=0.0)
    ink, _muted, _grid = chart_furniture(ctx)

    if vertical:
        fig, axes = new_figure_grid(ctx, len(groups))
        x = np.arange(n_cat)
        titled: list[tuple[object, str]] = []
        drawn: list[tuple] = []
        for ax, (p, segs) in zip(axes, groups):
            n = len(segs)
            clrs = panel_colours(segs)
            w = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * w if n > 1 else 0.0
                ax.bar(x + off, [v or 0.0 for v in vals], width=w, color=clrs[i],
                       edgecolor="none", zorder=3)
                drawn.append((ax, x + off, vals, w))
            titled.append((ax, p))
            ax.set_xticks(x)
            ax.set_xticklabels(_category_ticks(cats, _wrap_xtick_label, series.statistic), fontsize=8.5,
                               color=ink, rotation=_XTICK_ROTATION, ha="right",
                               rotation_mode="anchor")
            register_category_labels(ax, "x", _category_ticks(cats, str, series.statistic),
                                     wrap=_wrap_label, width=_XLABEL_WRAP_WIDTH)
            _apply_column_style(ax, ctx, max_val, series.statistic)
    else:
        fig, axes = new_figure_grid(ctx, len(groups), tall_in=n_cat * 0.42 + 2.0)
        y = np.arange(n_cat)[::-1]
        titled = []
        drawn = []
        for k, (ax, (p, segs)) in enumerate(zip(axes, groups)):
            n = len(segs)
            clrs = panel_colours(segs)
            h = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * h if n > 1 else 0.0
                ax.barh(y + off, [v or 0.0 for v in vals], height=h, color=clrs[i],
                        edgecolor="none", zorder=3)
                drawn.append((ax, y + off, vals, h))
            titled.append((ax, p))
            ax.set_yticks(y)
            _apply_bar_style(ax, ctx, max_val, series.statistic)
            # y-axis is SHARED (sharey) → set the category labels ONCE, then hide their
            # DISPLAY on the other panels (clearing them would clear the shared axis).
            if k == 0:
                ax.set_yticklabels(_category_ticks(cats, _wrap_label, series.statistic), fontsize=9, color=ink)
                register_category_labels(ax, "y", _category_ticks(cats, str, series.statistic),
                                         wrap=_wrap_label, width=_LABEL_WRAP_WIDTH)
            ax.tick_params(axis="y", labelleft=(k == 0))

    panel_legends = []
    if ctx.spec.elements.legend:
        # One legend PER PANEL. "Naiset" is 240 people in one panel and 261 in
        # the next, and a legend shared by the row can say only one of them.
        # Colours stay keyed by position, the same in every panel.
        for ax, (_p, segs) in zip(axes, groups):
            clrs = panel_colours(segs)
            names = [_group_name(series, s, show_base=wants_group_base(ctx)) for s in segs]
            handles = [Patch(facecolor=clrs[i], edgecolor="none") for i in range(len(names))]
            panel_legends.append((ax, handles, names))
    fig.subplots_adjust(bottom=0.24, wspace=0.12, top=0.9,
                        left=0.12 if vertical else 0.2)
    # Once the panels are laid out, so both are fitted to the width they have.
    _label_panel_bars(fig, ctx, drawn, vertical=vertical, n_cat=n_cat,
                      all_vals=all_vals, max_val=max_val, ink=ink)
    if not vertical:
        _thin_panel_ticks(fig, axes)
    fit_panel_titles(fig, titled, colour=ink)
    if panel_legends:
        _panel_legends(fig, panel_legends, max_ncol=3)
    separate_panel_rows(fig)
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
#: CLEAR air between two side-by-side panels, on top of whatever room the
#: labels drawn into that gap need.
#:
#: The gap used to be exactly `label width + _LABEL_PAD_IN`, and matplotlib
#: draws a panel's tick labels immediately left of its own axes — so the labels
#: filled the gap and the only clear space was that 0.12" pad. Wide enough not
#: to OVERLAP, which is what the arithmetic solved for, and far too tight to
#: read as two separate charts: "kaaviot ovat tässä hieman liian lähekkäin".
#: Added rather than substituted, so a wide label still gets its room.
#: (Johan, 2026-09-10)
_MIN_PANEL_GAP_IN: float = 0.45
#: Clear space between the secondary label block and the rotated primary group
#: label standing to its left, so the two read as two columns and not one smudge.
_GROUP_LABEL_PAD_IN: float = 0.18
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
    span_in = max(0.0, (right_frac - left_frac) * fig_w_in)
    base_gap_in = gap_label_w_in + _LABEL_PAD_IN      # room the labels need
    if n_panels > 1:
        # As much air as fits WITHOUT changing the side-by-side decision. This
        # function answers both "how wide is the gap" and (through plot_w_in)
        # "do these panels fit side by side at all", so simply adding the
        # minimum would restack layouts that were fine — measured: three
        # three-panel cases near the threshold flipped, a far bigger change
        # than the one asked for. Where the air does not fit, the panels were
        # already at their narrowest and the caller stacks them as it did
        # before. (Johan, 2026-09-10)
        affordable = ((span_in - n_panels * _MIN_HGUTTER_PLOT_IN) / (n_panels - 1)
                      if span_in else base_gap_in)
        gap_in = max(base_gap_in,
                     min(base_gap_in + _MIN_PANEL_GAP_IN, affordable))
    else:
        gap_in = 0.0
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
    default_order = dict(groups)          # colours are dealt along this, per panel
    # Each panel keeps its own "<variable> · Total". A horizontal panel stacks a
    # group's bars from the bottom up, so there the reader's top is the list's end.
    groups = [(p, place_total(segs, _total_position(ctx), top_is_last=not vertical))
              for p, segs in groups]
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

    titled: list[tuple[object, str]] = []
    panel_legends: list[tuple[object, list, list[str]]] = []
    drawn: list[tuple] = []
    for k, (ax, (p, segs)) in enumerate(zip(axes, groups)):
        n = len(segs)
        clrs = colours_by_series(series_colors(n, palette=template_palette(ctx),
                                               accent=chart_accent(ctx)),
                                 coded_order(series, default_order.get(p, segs)), segs)
        if vertical:
            x = np.arange(n_cat)
            w = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * w if n > 1 else 0.0
                ax.bar(x + off, [v or 0.0 for v in vals], width=w, color=clrs[i],
                       edgecolor="none", zorder=3)
                drawn.append((ax, x + off, vals, w))
            ax.set_xticks(x)
            ax.set_xticklabels(_category_ticks(cats, _wrap_xtick_label, series.statistic), fontsize=8.5,
                               color=ink, rotation=_XTICK_ROTATION, ha="right",
                               rotation_mode="anchor")
            register_category_labels(ax, "x", _category_ticks(cats, str, series.statistic),
                                     wrap=_wrap_label, width=_XLABEL_WRAP_WIDTH)
            _apply_column_style(ax, ctx, max_val, series.statistic)
        else:
            y = np.arange(n_cat)[::-1]
            h = 0.82 / n if n > 1 else 0.6
            for i, seg in enumerate(segs):
                vals = data.get(seg, [None] * n_cat)
                off = (i - n / 2 + 0.5) * h if n > 1 else 0.0
                ax.barh(y + off, [v or 0.0 for v in vals], height=h, color=clrs[i],
                        edgecolor="none", zorder=3)
                drawn.append((ax, y + off, vals, h))
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
                ax.set_yticklabels(_category_ticks(cats, _wrap_label, series.statistic), fontsize=9, color=ink)
            ax.tick_params(axis="y", labelleft=first_in_row)
            if first_in_row:
                register_category_labels(ax, "y", _category_ticks(cats, str, series.statistic),
                                         wrap=_wrap_label, width=_LABEL_WRAP_WIDTH)
        # Each panel is titled with its VARIABLE, not with a group of the first one.
        titled.append((ax, p))
        if ctx.spec.elements.legend:
            names = [_group_name(series, s, show_base=wants_group_base(ctx)) for s in segs]
            handles = [Patch(facecolor=clrs[i], edgecolor="none") for i in range(len(names))]
            panel_legends.append((ax, handles, names))

    fig.subplots_adjust(bottom=0.24, wspace=wspace_frac, hspace=0.45, top=0.9,
                        left=left_frac, right=right_frac)
    _label_panel_bars(fig, ctx, drawn, vertical=vertical, n_cat=n_cat,
                      all_vals=all_vals, max_val=max_val, ink=ink)
    if not vertical:
        _thin_panel_ticks(fig, axes)
    # Fitted once the panels are laid out: both are as wide as their own panel
    # and the half-gutter beside it, and no wider.
    fit_panel_titles(fig, titled, colour=ink)
    if panel_legends:
        _panel_legends(fig, panel_legends, max_ncol=4)
    # Each panel's band — title, plot, names, legend — clear of its neighbour's.
    separate_panel_rows(fig)
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


def _as_one_series_per_group(ctx, cats, segs, data):
    """A summary chart, transposed: the GROUPS become the categories.

    `_summary` reports one value per group as one category (the measure itself)
    × N segments, which is true but is not how the chart reads. Drawn literally,
    the segments split a single category slot: at four groups that is four bars
    of 0.175 flush against each other, filling most of an axis that has one slot
    to fill — the "tosi leveitä ja kiinni toisissaan" of the report.

    Transposing hands it to the ordinary path as what it actually is: one series
    over N categories. Bar width, spacing, the single series colour, the names
    on the axis and the absent legend all follow from there rather than being
    special-cased here. (Johan, 2026-09-09)
    """
    if len(cats) != 1 or len(segs) < 2:
        return cats, segs, data
    if getattr(ctx.series, "statistic", "") not in _SUMMARY_STATISTICS:
        return cats, segs, data
    lone = cats[0]
    return list(segs), [lone], {lone: [data[seg][0] for seg in segs]}


def _render_column_v(ctx, cats, segs, data) -> None:
    """Internal vertical-bar renderer."""
    cats, segs, data = _as_one_series_per_group(ctx, cats, segs, data)
    # Columns are read left to right, and a group's bars in the order listed.
    default_segs, segs = coded_order(ctx.series, segs), place_total(segs, _total_position(ctx))
    cats, data = _place_total_category(cats, data, _total_position(ctx))
    fig, ax = new_figure(ctx)
    clrs = colours_by_series(series_colors(len(segs), palette=template_palette(ctx),
                                           accent=chart_accent(ctx)),
                             default_segs, segs)

    n_cats = len(cats)
    n_segs = len(segs)
    x = np.arange(n_cats)
    width = 0.7 / n_segs if n_segs > 1 else 0.5

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=0.0)
    ink, _muted, _grid = chart_furniture(ctx)

    # Cross-tab: pull the bars apart into primary-classifier groups (gap between groups).
    grouped = _grouped_offsets(segs, ctx.series.segment_primary)
    _value_fit: tuple[float, float] | tuple[()] | None = None

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
            label=series_label(ctx, seg), color=bar_clrs,
            edgecolor="none", zorder=3,
        )
        off = _label_offset(max_val)
        # Measured once for the whole chart, against the WIDEST number it will
        # draw, so every column is labelled the same way or none is — a row
        # where some carry a number and others do not reads as a fault.
        if _value_fit is None:
            _widest = max((format_value(v, ctx.series.statistic,
                                        ctx.spec.number_format, all_vals)
                           for v in all_vals), key=len, default="")
            _value_fit = _value_label_layout(fig, ax, n_cats, bwidth, _widest) or ()
        _floor = author_label_floor(ctx.spec, ctx.series.statistic, all_vals)
        for bar, v in zip(bars, vals):
            if v is not None and _value_fit and v >= _floor:
                _pt, _rot = _value_fit
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + off,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    # Aligned AFTER turning (matplotlib's default mode): the
                    # turned number's box stands on the bar, centred on it.
                    # `rotation_mode="anchor"` aligned it before turning, so
                    # "center" put the MIDDLE of the upright number on the bar
                    # top and "bottom" pushed it left — half of "43 %" inside a
                    # dark bar, reported as "pylväiden numeroiden formaatissa on
                    # jotain outoa". (2026-09-19)
                    ha="center", va="bottom", rotation=_rot,
                    fontsize=_pt, fontweight="bold", color=ink, zorder=5,
                    gid=VALUE_GID,
                )

    # Wrap + rotate x-axis labels so they are shown in full and never overlap.
    display_cats = _category_ticks(cats, _wrap_xtick_label, ctx.series.statistic)
    ax.set_xticks(x)
    ax.set_xticklabels(
        display_cats, fontsize=10.5, color=ink,
        rotation=_XTICK_ROTATION, ha="right", rotation_mode="anchor",
    )
    register_category_labels(ax, "x", _category_ticks(cats, str, ctx.series.statistic),
                             wrap=_wrap_label, width=_XLABEL_WRAP_WIDTH)
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
    # Same transposition as the vertical form: one value per group is a chart
    # of GROUPS, whichever way its bars run.
    cats, segs, data = _as_one_series_per_group(ctx, cats, segs, data)
    # Categories run top to bottom in the order listed, but a group's own bars
    # are stacked from the bottom UP — so there the reader's top is the end of
    # the list, which is why Total, last, has always been each group's top bar.
    default_segs, segs = coded_order(ctx.series, segs), place_total(segs, _total_position(ctx), top_is_last=True)
    cats, data = _place_total_category(cats, data, _total_position(ctx))
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
    clrs = colours_by_series(series_colors(len(segs), palette=template_palette(ctx),
                                           accent=chart_accent(ctx)),
                             default_segs, segs)

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
            label=series_label(ctx, seg), color=bar_clrs,
            edgecolor="none", zorder=3,
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

    # Decided once, for the whole chart, and RECORDED. Dropping the numbers is
    # right — at this height a label would overlap its neighbours — but it used
    # to happen in silence: the author got a chart with no numbers, no reason,
    # and no hint that the same chart labels perfectly on a taller chart area.
    # The note reaches them in the editor; nothing is printed on the slide.
    # (Johan, 2026-09-16)
    labelled = per_bar_pt >= _MIN_LABEL_BAR_PT
    if not labelled and all_vals:
        note(ctx, "unlabelled", n_cats)

    off = _label_offset(max_val)
    for i, seg in enumerate(segs):
        vals = data[seg]
        offset = (i - n_segs / 2 + 0.5) * height if n_segs > 1 else 0.0
        ys = y + offset
        _floor = author_label_floor(ctx.spec, ctx.series.statistic, all_vals)
        for yi, v in zip(ys, vals):
            if v is not None and labelled and v >= _floor:
                ax.text(
                    v + off, yi,
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    va="center", ha="left",
                    fontsize=value_fs, fontweight="bold", color=ink, zorder=5,
                    gid=VALUE_GID,
                )

    # Wrap y-axis labels; cap to the lines that fit the band (ellipsis last resort).
    display_cats = _category_ticks(
        cats, lambda c: wrap_label_capped(c, _HBAR_LABEL_WRAP_WIDTH, max_lines),
        ctx.series.statistic)
    ax.set_yticks(y)
    ax.set_yticklabels(display_cats, fontsize=ylabel_fs, color=ink)
    register_category_labels(ax, "y", _category_ticks(cats, str, ctx.series.statistic),
                             wrap=_wrap_label, width=_HBAR_LABEL_WRAP_WIDTH)
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

def _stacked_layout(series, total_position: str = "auto"):
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
    # The first bar is drawn at the top (horizontal) or on the left (vertical).
    bars = place_total(bars, total_position)
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
    totals = [sum(data[s][i] or 0.0 for s in stack) for i in range(len(bars))]
    # An all-zero or empty chart has no scale to read; keep the 0-100 axis it
    # always had rather than collapsing every limit onto zero.
    true_widths = (False, max(totals, default=0.0) or 100.0)

    # A statistic that does not ADD does not partition anything, and that is
    # knowledge, not missing information. A mean is not a share of a base:
    # there is no whole for it to be part of, so filling a bar to 100 with it
    # states a composition the data never claimed.
    #
    # The rule below deliberately lets an UNJUDGEABLE bar keep the 100 %
    # reading — absence of evidence is not evidence of overlap — and a
    # mean-statistic bar is unjudgeable by `_bar_is_measurable`. With every bar
    # in that state the `all()` was vacuously True, so the two rules together
    # normalised a chart nothing had vouched for. Työelämäindeksi crossed by
    # pride then drew eight identical full-width bars carrying 3.0, 3.6, 4.3,
    # 4.9, 5.5, 6.1, 6.7 and 5.7 — each bar normalised against its own total,
    # so groups more than a scale point apart came out the same length. The
    # printed number true and the picture false: the very failure the
    # multi-response case above exists to prevent.
    #
    # Asked BEFORE measurability, because it is a different question. This one
    # is "can these values be a composition at all", which `ADDITIVE_STATISTICS`
    # answers for the pie in exactly the same way (`charts/pie.py`).
    if getattr(series, "statistic", "pct") not in ADDITIVE_STATISTICS:
        return true_widths

    normalise = all(
        series.is_partition(b, undershoot_tol=PARTITION_UNDERSHOOT_TOL_PCT)
        for b in bars if _bar_is_measurable(series, b)
    )
    if normalise:
        return True, 100.0
    return true_widths


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
    bars_all, stack, data = _stacked_layout(series, _total_position(ctx))
    # Decided across ALL panels' bars, and the axis maximum shared by every panel:
    # panels of one chart are read against each other, so they must not scale
    # independently. (See `_stack_scaling`.)
    normalise, axis_max = _stack_scaling(series, bars_all, stack, data)
    # `bars_all` is base-filtered; a variable whose every group is near-empty keeps
    # no bar at all, and a panel with no bars used to reach `min(y)` on an empty
    # sequence (ValueError). It is omitted instead. (final review I3)
    groups = _drawable_panels(_primary_groups(series), bars_all)
    # Each panel keeps its own "<variable> · Total"; it goes where the author said.
    groups = [(p, place_total(bars, _total_position(ctx))) for p, bars in groups]
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
            [_wrap_label(b) for b in _bar_names(series, bars, short=True, show_base=wants_group_base(ctx))], 10.5)
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

    titled: list[tuple[object, str]] = []
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
        names = _bar_names(series, bars, short=True, show_base=wants_group_base(ctx))
        ax.set_yticklabels([_wrap_label(b) for b in names], fontsize=10.5, color=ink)
        register_category_labels(ax, "y", names, wrap=_wrap_label, width=_LABEL_WRAP_WIDTH)
        ax.tick_params(axis="y", labelleft=True)
        ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
        _apply_bar_style(ax, ctx, axis_max, "pct" if normalise else series.statistic)
        titled.append((ax, p))
        # per panel, keyed by bar — placed against the axis the bars were drawn on
        _draw_row_summary(ctx, ax, y, bars, ax.get_xlim()[1])

    if ctx.spec.elements.legend and len(stack) > 1:
        _legend_below(axes[-1], len(stack), ctx)
    fig.subplots_adjust(bottom=0.24, wspace=wspace_frac, hspace=0.45, top=0.9,
                        left=left_frac, right=right_frac)
    fit_panel_titles(fig, titled, colour=ink)
    separate_panel_rows(fig)
    for _panel_ax in axes:
        make_room_for_values(fig, _panel_ax)
        clear_callouts(fig, _panel_ax, along="x")
        shrink_values_until_clear(fig, _panel_ax)
    place_picture(ctx, render_png(fig))


def build_image_column_stacked(ctx) -> None:
    """Stacked vertical bar chart: bars = classifier segments, stack = answer
    categories (house style). Normalised to 100% per column where the stack really
    partitions the column's base, otherwise drawn at true heights
    (`_stack_scaling`) — the horizontal builder's rule, applied to columns."""
    cats, segs, data = _stacked_layout(ctx.series, _total_position(ctx))
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
            # Full size when it fits; a thin segment's number smaller INSIDE it
            # before it is sent outside (see `_draw_stacked_panel._size`) — a
            # number's width and height both scale with its size.
            _scale = min(1.0, h / (_h * 1.15), bar.get_width() / (_w * 1.06))
            if 9.0 * _scale >= _VALUE_MIN_PT:
                ax.text(
                    x_mid, b + h / 2, text, ha="center", va="center",
                    fontsize=9.0 * _scale, fontweight="bold",
                    color=contrast_ink(bar.get_facecolor()), zorder=5, gid=_VALUE_GID,
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
        secondary = _bar_names(ctx.series, cats, short=True, show_base=wants_group_base(ctx))
        # Flat under its column when it fits there, as it always was. Rotated,
        # like an ungrouped column chart's names, when it does not: eighteen
        # columns of "Suomi (n=1016)" printed flat ran into each other, and no
        # size above the floor made them fit. (Johan, 2026-09-11)
        x0, x1 = ax.get_xlim()
        pitch_px = ax.bbox.width / max(abs(x1 - x0), 1e-6)
        widest_px = max((_text_extent_px(fig, s, 9.5)[0] for s in secondary), default=0.0)
        depth_px = None
        if widest_px <= pitch_px * 0.92:
            ax.set_xticklabels(secondary, fontsize=9.5, color=ink)
        else:
            ax.set_xticklabels(secondary, fontsize=9.5, color=ink, rotation=_XTICK_ROTATION,
                               ha="right", rotation_mode="anchor")
            a = math.radians(_XTICK_ROTATION)
            line_px = 9.5 * 1.25 * fig.dpi / 72.0
            depth_px = widest_px * math.sin(a) + line_px * math.cos(a) + 6.0 * fig.dpi / 72.0
        register_category_labels(ax, "x", secondary, wrap=_wrap_label)
        _draw_group_labels_under(fig, ax, grouped[1],
                                 _group_sizes(cats, ctx.series.segment_primary), ink,
                                 names_depth_px=depth_px)
    else:
        # Wrap + rotate x-axis labels so they are shown in full and never overlap.
        names = _bar_names(ctx.series, cats, short=False, show_base=wants_group_base(ctx))
        ax.set_xticklabels(
            [_wrap_xtick_label(c) for c in names], fontsize=10.5, color=ink,
            rotation=_XTICK_ROTATION, ha="right", rotation_mode="anchor",
        )
        register_category_labels(ax, "x", names, wrap=_wrap_label, width=_XLABEL_WRAP_WIDTH)
    # Normalised → the axis IS the 0-100 composition scale, whatever statistic the
    # columns carry. True heights → the axis must read the data's own statistic.
    _apply_column_style(ax, ctx, axis_max, "pct" if normalise else ctx.series.statistic)

    if ctx.spec.elements.legend and len(segs) > 1:
        _legend_below(ax, len(segs), ctx)

    # A called-out number sitting on another moves beside its column first;
    # anything still crowded is shrunk until it stands clear. Nothing is ever
    # taken off the slide — a number with nowhere to go stays and gets smaller.
    make_room_for_values(fig, ax)
    clear_callouts(fig, ax, along="y")
    shrink_values_until_clear(fig, ax)

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


#: Marks a drawn VALUE label — a number inside a bar, or one called out beside
#: it. Both carry it so one pass can find every number on a panel.
#: Kept as a module-local name: three test modules and the callout/shrink
#: passes below import it from here.
_VALUE_GID = VALUE_GID
#: The smallest a value label may be shrunk to before it stops being worth
#: printing. Below this it is decoration on a slide, not a figure someone reads.
_VALUE_MIN_PT: float = 6.5
#: Clear air two numbers on one row must keep between them, in ems of their own
#: type. Not overlapping is not enough: "2 %2 %" on the customer's sector slide
#: had its two boxes 0.108 em apart — touching, reading as one number, and
#: passing every overlap test there was. Names already keep this much.
_VALUE_GAP_EM: float = 0.2


def shrink_values_until_clear(fig, ax, *, min_pt: float = _VALUE_MIN_PT,
                              step: float = 0.85, tries: int = 5) -> float | None:
    """Shrink this panel's value labels until none overlaps another.

    A LAST resort, and deliberately a post-pass: it changes only type size,
    never a position, so a panel whose numbers already sit clear is left
    byte-identical. That property is why this is safe where moving them was
    not — two attempts at nudging the callouts sideways made the overlap worse
    (6 pairs became 15), because a callout pushed clear of an in-bar number
    overflows the axis and the overflow correction drags the run back onto it.

    The collision is mostly VERTICAL: a callout sits about 12px above its bar
    and an in-bar number at the bar's centre, which clears at six rows and does
    not at eighteen, where a row is 44px and 9pt text is 25px. Smaller type is
    shorter as well as narrower, so it buys back the clearance directly.

    Returns the size settled on, or None when nothing had to change.
    (Johan, 2026-09-10)
    """
    # Each number by its own box: a callout's window extent also wraps its
    # leader line, whose box covers ground the line never touches, and that
    # alone shrank every number on a chart where none overlapped.
    # (Johan, 2026-09-11)
    from matplotlib.text import Text

    labels = [t for t in ax.texts if t.get_gid() == _VALUE_GID and t.get_visible()]
    if len(labels) < 2:
        return None

    def clashes() -> bool:
        """Not merely "do they overlap" — do they stand APART.

        Two numbers a hair's breadth apart read as one: "2 %2 %" on the
        customer's sector slide had its boxes 2.27px apart, 0.108 em, not
        overlapping by a single pixel. Judged clear by an overlap test, and
        wrong to any reader. So numbers on one row must keep `_VALUE_GAP_EM`
        of their own type size between them, which is the same rule names
        already keep. (Johan, 2026-09-13)
        """
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        boxed = [(t, Text.get_window_extent(t, r)) for t in labels]
        for i, (ta, a) in enumerate(boxed):
            for tb, b in boxed[i + 1:]:
                share_a_row = min(a.y1, b.y1) - max(a.y0, b.y0) > 0.5
                if not share_a_row:
                    continue
                # Negative when the boxes interpenetrate.
                gap_px = max(a.x0, b.x0) - min(a.x1, b.x1)
                em_px = max(ta.get_fontsize(), tb.get_fontsize()) * fig.dpi / 72.0
                if gap_px < _VALUE_GAP_EM * em_px:
                    return True
        return False

    def crowded_pairs():
        """The pairs that are too close, worst first — not a yes/no."""
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        boxed = [(t, Text.get_window_extent(t, r)) for t in labels]
        out = []
        for i, (ta, a) in enumerate(boxed):
            for tb, b in boxed[i + 1:]:
                if min(a.y1, b.y1) - max(a.y0, b.y0) <= 0.5:
                    continue
                gap_px = max(a.x0, b.x0) - min(a.x1, b.x1)
                em_px = max(ta.get_fontsize(), tb.get_fontsize()) * fig.dpi / 72.0
                short = _VALUE_GAP_EM * em_px - gap_px
                if short > 0:
                    out.append((short, ta, tb))
        out.sort(key=lambda p: -p[0])
        return out

    def _overlap_area() -> float:
        """How much ink actually sits on other ink, in square pixels.

        A measure rather than a yes/no, because the two cases look identical to
        a boolean and want opposite answers: two numbers printed at the SAME
        point overlap however small they are, and shrinking is the only thing
        that helps them; two numbers a row apart on a slot too narrow for them
        overlap just as stubbornly, and shrinking buys nothing at all. The area
        falling tells one from the other. (Johan, 2026-09-13)
        """
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        boxed = [Text.get_window_extent(t, r) for t in labels]
        total = 0.0
        for i, a in enumerate(boxed):
            for b in boxed[i + 1:]:
                dx = min(a.x1, b.x1) - max(a.x0, b.x0)
                dy = min(a.y1, b.y1) - max(a.y0, b.y0)
                if dx > 0.5 and dy > 0.5:
                    total += dx * dy
        return total

    def interpenetrating() -> bool:
        return _overlap_area() > 0.0

    crowded = crowded_pairs()
    if not crowded:
        return None
    before_area = _overlap_area()
    was_overlapping = before_area > 0.0
    restore = [(t, t.get_fontsize()) for t in labels]
    # Only the numbers that are actually too close get smaller.
    #
    # Scaling the whole panel took every one of the customer's 121 numbers from
    # 9pt to 7.5pt to buy room for a single pair — and still did not buy it,
    # because the floor stopped the loop first. A chart where every figure is
    # smaller for the sake of two of them reads worse than the crowding did.
    # (Johan, 2026-09-13)
    def yields(t) -> bool:
        return t.get_fontsize() > min_pt + 1e-9

    for _ in range(tries):
        for _short, ta, tb in crowded:
            # The narrower segment's number is the one with nowhere to go, so
            # it yields first; its neighbour only follows if that is not enough.
            for t in sorted((ta, tb), key=lambda x: x.get_fontsize()):
                if not yields(t):
                    continue
                # Clamped to the floor, not refused at it. The customer's
                # slivers sat at 7.58pt, one step from which is 6.44 — under
                # the 6.5 floor — so refusing the step left them stuck 0.06pt
                # above it, touching, for ever. Going to 6.5 exactly is 14%
                # narrower, which is far more room than the pair needed.
                t.set_fontsize(max(min_pt, t.get_fontsize() * step))
                break
        crowded = crowded_pairs()
        if not crowded:
            break
        # Stop only when nothing left in a crowded pair can give. Testing the
        # SMALLER of each pair stopped the loop while the wider neighbour still
        # had room, which is how two labels at one point ended up with only one
        # of them shrunk. (Johan, 2026-09-13)
        if not any(yields(ta) or yields(tb) for _s, ta, tb in crowded):
            break
    # A shrink that bought NOTHING is worse than no shrink: on the narrowest
    # slot both numbers went 9pt -> 6.5pt and still sat on each other, so the
    # chart paid a third of its type size for nothing. Put it back and leave
    # the crowding visible rather than small AND crowded.
    #
    # Only when it bought nothing, though. Two numbers printed at the same
    # point overlap however small they are, and there shrinking IS the answer —
    # reverting it there undid the one thing that helps. (Johan, 2026-09-13)
    if was_overlapping and interpenetrating() and _overlap_area() >= before_area:
        for t, pt in restore:
            t.set_fontsize(pt)
        return None
    return min(t.get_fontsize() for t in labels)


def make_room_for_values(fig, ax, *, max_grow: float = 0.3,
                         passes: int = 3) -> bool:
    """Grow the axis until every value label is inside the plot.

    A number too big for its own piece is called out BESIDE that piece. Where
    the piece is at the edge of the chart — the top row of a stack, the tallest
    column, a sliver whose neighbour has already pushed it up a line — the
    place the callout needs is outside the axis, and `annotation_clip=False`
    draws it there: a "2 %" floating above the plot frame, joined to its
    segment by a line crossing the boundary.

    Clipping it would be worse; it takes a figure the chart computed off the
    slide, and a reader cannot tell a suppressed 2 % from one that was never
    there. So the chart makes room instead. This is the counterpart of
    `_STACK_BAR_H_CALLOUT`, which already thins the bars to keep a gap BETWEEN
    rows for exactly these numbers — the edge is the case that gap logic cannot
    reach, because there is no neighbouring row to borrow from.

    Runs before `clear_callouts` so the declash pass sees the enlarged area.
    A panel whose numbers are already inside is left untouched and renders
    byte-identical, which is what makes this safe to apply everywhere.

    Growth is capped at *max_grow* of each axis's span: enough for a line or
    two of type, never enough to squash the data into a corner. Returns whether
    anything moved.
    """
    from matplotlib.text import Text

    grew = False
    for _ in range(max(1, passes)):
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        labels = [t for t in ax.texts
                  if t.get_gid() == _VALUE_GID and t.get_visible()]
        if not labels:
            return grew
        area = ax.get_window_extent(r)
        # The number's own box. A callout's window extent also wraps its leader
        # line, which reaches back to the segment and would ask for room the
        # text does not need. (Same reason the shrink pass measures this way.)
        boxes = [Text.get_window_extent(t, r) for t in labels]
        over = {
            "top": max((b.y1 - area.y1 for b in boxes), default=0.0),
            "bottom": max((area.y0 - b.y0 for b in boxes), default=0.0),
            "right": max((b.x1 - area.x1 for b in boxes), default=0.0),
            "left": max((area.x0 - b.x0 for b in boxes), default=0.0),
        }
        # Half a pixel is rounding, not an escape.
        if all(v <= 0.5 for v in over.values()):
            return grew

        # A little more than the overflow, so the number is not left touching
        # the frame it just cleared.
        pad = 0.25 * max(t.get_fontsize() for t in labels) * fig.dpi / 72.0

        def _stretch(get, set_, lo_px, hi_px):
            """Move one axis's limits out by a pixel amount at each end.

            Works in signed data-per-pixel, so an INVERTED axis — which is how
            a horizontal bar chart puts its first category at the top — grows
            at the end the overflow is actually on.
            """
            nonlocal grew
            lo, hi = get()
            span = hi - lo
            if not span:
                return
            per_px = span / max(area.height if set_ is ax.set_ylim
                                else area.width, 1e-9)
            cap = abs(max_grow * span)
            d_lo = min(abs(per_px) * (lo_px + pad), cap) if lo_px > 0.5 else 0.0
            d_hi = min(abs(per_px) * (hi_px + pad), cap) if hi_px > 0.5 else 0.0
            if not d_lo and not d_hi:
                return
            sign = 1.0 if span > 0 else -1.0
            set_(lo - sign * d_lo, hi + sign * d_hi)
            grew = True

        _stretch(ax.get_ylim, ax.set_ylim, over["bottom"], over["top"])
        _stretch(ax.get_xlim, ax.set_xlim, over["left"], over["right"])
    return grew


def clear_callouts(fig, ax, *, along: str) -> int:
    """Move each called-out number that sits on another number to the nearest
    clear place along its own row (`along="x"`) or column (`along="y"`).

    The customer's country × sector slide printed four of its 2 % callouts
    straight over the numbers inside the bar above — "4 %2 %" — and shrinking
    both, the earlier last resort, took six such pairs to four and no further.
    A callout already sits where its segment can be seen; what it lacked was
    room. So it keeps its side of the bar (a horizontal bar's number stays ABOVE
    its bar — below, it reads as the next bar's) and its line to its segment,
    and slides along until it touches nothing.

    It moves a short way only (a long line across other numbers is its own
    confusion). A callout with no clear place within that is left out — never
    printed over another number, and never the reason every number on the chart
    is shrunk.

    Works on the boxes as drawn, in the face the figure is saved in, so what it
    clears is what the reader sees. A panel whose numbers already sit clear is
    left exactly as it was. Returns how many moved or were left out.
    (Johan, 2026-09-11)"""
    values = [t for t in ax.texts if t.get_gid() == _VALUE_GID and t.get_visible()]
    callouts = [t for t in values if hasattr(t, "xyann")]
    if not callouts:
        return 0
    family = getattr(fig, "_nsight_chart_font", "")
    if family:
        for t in values:
            t.set_fontfamily(family)
    r = fig.canvas.get_renderer()
    # The NUMBER's own box. An annotation's window extent also wraps its leader
    # line, and once a callout has moved along, that line runs diagonally and
    # its box covers ground the line never touches — steering around it moved
    # callouts away from room that was free.
    from matplotlib.text import Text

    def text_box(t):
        # A callout's on-screen position is worked out during a draw; measured
        # before one, it was measured where it is not, and "cleared" onto a
        # number that was there all along.
        if hasattr(t, "update_positions"):
            t.update_positions(r)
        return Text.get_window_extent(t, r)

    boxes = {id(t): text_box(t) for t in values}
    area = ax.bbox

    def touches(box, me) -> bool:
        return any(o is not me
                   and min(box.x1, boxes[id(o)].x1) - max(box.x0, boxes[id(o)].x0) > -1.0
                   and min(box.y1, boxes[id(o)].y1) - max(box.y0, boxes[id(o)].y0) > -1.0
                   for o in values)

    moved, step = 0, 2.0
    for t in callouts:
        box = boxes[id(t)]
        if not touches(box, t):
            continue
        # A short way only. Moved far, a callout pulls a long line across other
        # numbers and ends up nearer another bar's segment than its own; past
        # this, shrinking is the better last resort.
        # Along its own row first, then ACROSS it. On a crowded horizontal bar
        # the collision is vertical — a callout sits ~12px above its bar and
        # the number inside the bar above sits at that bar's centre — so
        # searching sideways scans the one direction that cannot help, finds
        # nothing, and hands a hopeless pair to the shrink, which then takes
        # both numbers to the floor and still leaves them overlapping.
        # At eighteen rows the pitch is ~38px against a 23px callout: the room
        # is there, just not on the axis we were looking along.
        # (Johan, 2026-09-13)
        shift, moved_axis = None, along
        for axis in (along, "y" if along == "x" else "x"):
            reach = 2.5 * (box.width if axis == "x" else box.height)
            # Across the row, a horizontal bar's number may only go UP. Below
            # its bar it reads as the next bar's number, however carefully the
            # line is drawn — so the downward candidate is not offered at all
            # rather than tried and rejected. (Johan, 2026-09-13)
            ups_only = axis == "y" and along == "x"
            k = 1
            while shift is None and k * step <= reach:
                for s in ((k * step,) if ups_only else (k * step, -k * step)):
                    cand = box.translated(s, 0) if axis == "x" else box.translated(0, s)
                    if axis == "x" and (cand.x0 < area.x0 or cand.x1 > area.x1):
                        continue
                    if axis == "y" and (cand.y0 < area.y0 or cand.y1 > area.y1):
                        continue
                    if not touches(cand, t):
                        shift, moved_axis = s, axis
                        break
                k += 1
            if shift is not None:
                break
        if shift is None:
            # Nowhere within reach is clear. It STAYS — left where it is, for
            # `shrink_values_until_clear` to make room for by size. It used to
            # be hidden here, which took a number the chart had computed off
            # the slide altogether: a reader cannot tell a suppressed 2 % from
            # a 2 % that was never there, and no amount of crowding justifies
            # publishing a chart that is missing one of its own figures.
            # (Johan, 2026-09-13)
            continue
        px, py = ax.transData.transform(t.xyann)
        t.xyann = tuple(ax.transData.inverted().transform(
            (px + shift, py) if moved_axis == "x" else (px, py + shift)))
        boxes[id(t)] = text_box(t)
        moved += 1
    return moved


def callout_value(ax, text: str, *, at, to, ink: str, grid: str,
                  ha: str = "center", va: str = "center") -> None:
    """One number that would not fit inside its own piece, drawn beside it.

    `at` is where the text goes, `to` the point on the piece it describes. The
    line between them is the whole point: without it a number floating near a
    stack of slivers belongs to any of them.
    """
    ax.annotate(text, xy=to, xytext=at, ha=ha, va=va, fontsize=8.5,
                fontweight="bold", color=ink, annotation_clip=False, zorder=6,
                gid=_VALUE_GID,
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

    def _size(seg, j) -> float | None:
        """The size this cell's number is printed INSIDE its segment at, or None
        when it does not fit even at the floor and must be called out.

        Full size when it fits. A thin segment's number is set smaller inside it
        before it is sent outside: on a dense chart the gap between two bars is
        thinner than a number, so a called-out "2 %" lands over the bar above —
        on its numbers ("4 %2 %"), or, moved clear of them, on its fill, where it
        reads as that bar's. Inside, it is only ever its own segment's.
        (Johan, 2026-09-11)"""
        w, need = _width(seg, j), room[said[(seg, j)]]
        if w >= need:
            return 9.0
        size = 9.0 * w / need                # a number's width scales with its size
        return size if size >= _VALUE_MIN_PT else None

    def _fits(seg, j) -> bool:
        return _size(seg, j) is not None

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
                        ha="center", va="center", fontsize=_size(seg, j), fontweight="bold",
                        color=contrast_ink(bc), zorder=5, gid=_VALUE_GID)
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
    cats, segs, data = _stacked_layout(ctx.series, _total_position(ctx))
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
    plan = ("rotated", {}, 0.0)
    if grouped:
        maxp = max(grouped[0])
        y = np.array([maxp - p for p in grouped[0]])   # first cat at top
        secondary = _bar_names(ctx.series, cats, short=True, show_base=wants_group_base(ctx))
        # Decided BEFORE the bars are drawn: a written-out group name takes a
        # column of the figure, and the panel measures which numbers fit inside
        # their segments against the plot as it is when it draws them.
        has_summary = any(v is not None for v in _row_summary_by_bar(ctx.series, cats))
        span = (max(y) + (1.2 if has_summary else 0.5)) - (min(y) - 0.7)
        plan = _plan_group_labels_beside(
            fig, grouped[1], _group_sizes(cats, ctx.series.segment_primary),
            ax.bbox.height / max(span, 1e-6))
        if plan[0] == "written":
            gutter_in = _measure_max_label_width_in(secondary, 10.5) + _LABEL_PAD_IN
            need = ((gutter_in + _GROUP_LABEL_PAD_IN + plan[2] + _LABEL_PAD_IN)
                    / fig.get_size_inches()[0])
            if need > ax.get_position().x0:
                fig.subplots_adjust(left=min(need, 0.6))
    else:
        y = np.arange(n_cats)[::-1]
    flat_vals = [v for seg in segs for v in data[seg] if v is not None]

    normalise, axis_max = _stack_scaling(ctx.series, cats, segs, data)
    _draw_stacked_panel(ax, cats, segs, data, clrs, ctx, y, flat_vals,
                        normalise=normalise, axis_max=axis_max)

    ax.set_yticks(y)
    if grouped:
        # Per-bar tick = the SECONDARY value; the primary is a group label to the
        # left. Both RIGHT-aligned against the axis, so the secondary block ends
        # in a straight edge and the primary stands clear of its widest line.
        ax.set_yticklabels(secondary, fontsize=10.5, color=ink, ha="right")
        # The rotated group names placed below are obstacles to the fit, so a
        # refitted name can never grow into them.
        register_category_labels(ax, "y", secondary, wrap=_wrap_label)
        # MEASURED, not a fixed -0.13. That constant is a fraction of the PLOT
        # width, so it meant "13% of the plot" — enough for "Total", nowhere
        # near enough for "hyvinvointialueen palveluksessa", which ran 205px
        # straight through the country name beside it. (Johan, 2026-09-10)
        plot_w_in = max(ax.get_position().width * fig.get_size_inches()[0], 0.1)
        gutter_in = _measure_max_label_width_in(secondary, 10.5) + _LABEL_PAD_IN
        # Beside the names, not out at the edge of the room reserved for them.
        #
        # `gutter_in` is the width of the LONGEST secondary name, and the names
        # are drawn ha="right", so only that one reaches back across the whole
        # gutter — every other row's name ends well short of it. Pinning the
        # group label at the gutter's outer edge therefore left a band of blank
        # paper that no text ever occupies: measured on the customer's slide,
        # 87px between "Suomi" and the nearest name it labels.
        #
        # A rotated label is only its own line-height wide, so it is placed a
        # pad left of where the names actually BEGIN. The gutter itself is
        # unchanged — the reservation still has to fit the longest name; this
        # only stops the label floating at the far side of it.
        # (Johan, 2026-09-13)
        group_x = -(gutter_in + _GROUP_LABEL_PAD_IN) / plot_w_in
        for glabel, gpos in grouped[1]:
            if plan[0] == "rotated":
                ax.text(group_x, maxp - gpos, glabel, transform=ax.get_yaxis_transform(),
                        ha="center", va="center", rotation=90,
                        fontsize=_GROUP_FS, fontweight="bold", color=ink, gid=_GROUP_GID)
            else:
                # Written out, its right edge where a rotated name's centre stood.
                wrapped, fs = plan[1][glabel]
                ax.text(group_x, maxp - gpos, wrapped, transform=ax.get_yaxis_transform(),
                        ha="right", va="center", multialignment="left",
                        fontsize=fs, color=ink, gid=_GROUP_GID)
    else:
        # Wrap long y-axis labels onto as many lines as needed (full text, no '…').
        names = _bar_names(ctx.series, cats, short=False, show_base=wants_group_base(ctx))
        ax.set_yticklabels([_wrap_label(c) for c in names], fontsize=11.5, color=ink)
        register_category_labels(ax, "y", names, wrap=_wrap_label, width=_LABEL_WRAP_WIDTH)
    ax.set_ylim(min(y) - 0.7, max(y) + 0.5)
    # Normalised → the axis IS the 0-100 composition scale, whatever statistic the
    # bars carry. True widths → the axis must read the data's own statistic.
    _apply_bar_style(ax, ctx, axis_max, "pct" if normalise else ctx.series.statistic)
    # right-hand per-row column (if configured), against the axis just applied
    _draw_row_summary(ctx, ax, y, cats, ax.get_xlim()[1])

    if ctx.spec.elements.legend and len(segs) > 1:
        _legend_below(ax, len(segs), ctx)

    # A called-out number sitting on another moves along its row first;
    # shrinking is the last resort. Nothing is ever taken off the slide.
    make_room_for_values(fig, ax)
    clear_callouts(fig, ax, along="x")
    shrink_values_until_clear(fig, ax)

    png = render_png(fig)
    place_picture(ctx, png)


# ---------------------------------------------------------------------------
# Shared legend styler (thin wrapper around the shared helper in _mpl)
# ---------------------------------------------------------------------------

def _style_legend(ax, ctx, loc: str = "best") -> None:
    """Apply house-style formatting to an axes legend."""
    style_legend(ax, ctx, loc)
