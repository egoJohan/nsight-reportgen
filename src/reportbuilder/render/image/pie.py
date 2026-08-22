"""Image-mode pie and doughnut chart builders — nSight house style (REQ-C-24/25/27a).

Builders: build_image_pie, build_image_doughnut.

House style:
- Slide-background bg, Liberation Sans font
- Teal ramp for slice colours (single series → TEAL, multi-slice → spread)
- Percentage labels on slices that are large enough; a category legend (with the
  value) sits beside the pie so labels are ALWAYS readable and NEVER overlap,
  even when several slices are tiny / near-zero.
- No matplotlib title (handled by slide chrome, REQ-D-04)
- Only suitable for single-choice parts-of-whole questions

Furniture (legend frame/text, wedge separators) is derived from the slide's own
background via `chart_furniture`/`chart_background` — INK/MUTED/GRIDC/CREAM
unchanged on a light slide (byte-identical to before this existed), flipped for
legibility on a dark one.

Circular aspect & fit (Task A): the pie is drawn on a square axes with
``set_aspect("equal")`` so the wedges form a true circle.  The category legend
is placed OUTSIDE the pie axes (to the right), so the saved PNG keeps the circle
geometry intact and ``place_picture_square`` scales the whole image to fit inside
the slot *preserving its real aspect ratio* — the pie is always circular and
fully contained, never squished into an oval.

Each renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.
"""
from __future__ import annotations

import textwrap

import matplotlib
matplotlib.use("Agg")
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402

from reportbuilder.render.image._mpl import (chart_accent,
    render_png, place_picture_square, format_value,
    chart_background, chart_furniture,
)
from reportbuilder.render.house_style import (
    register_fonts, series_colors, contrast_ink, MUTED,
)
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL
from reportbuilder.render.image._mpl import template_palette
from reportbuilder.render.panels import panel_segments

_EMU_PER_IN = 914400.0

# Legend category text is wrapped (never ellipsis-cut) so long options stay
# compact and don't blow the legend out sideways.
_LEGEND_WRAP: int = 26
# Only annotate a wedge with its % when the slice is big enough to hold the text
# without colliding with a neighbouring label; every value is also in the legend.
_MIN_WEDGE_PCT: float = 4.0


def _wrap_legend_label(text: str) -> str:
    """Wrap a legend category label at word boundaries — full text, never '…'."""
    if len(text) <= _LEGEND_WRAP:
        return text
    return textwrap.fill(text, width=_LEGEND_WRAP, break_long_words=True)


def _make_square_fig_ax(ctx, bg: str):
    """Create a wide figure filling the slot, with the (square, set_aspect=equal)
    pie axes on the LEFT and room for the legend on the right.

    A square figure letterboxed the pie into the wide 4:3 slot, leaving big empty
    side margins so the circle looked small. Matching the slot's aspect and
    pinning the pie to the left lets it grow to the full slot HEIGHT and uses the
    whole width (pie + legend)."""
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    fig = Figure(figsize=(w_in, h_in), dpi=200)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(bg)
    # Pie axes: left ~62% of the width, full height — the circle fills the height.
    ax = fig.add_axes([0.0, 0.0, 0.62, 1.0])
    ax.set_facecolor(bg)
    return fig, ax


# Vertical share of the figure reserved for the shared legend under a panel row.
# This is only a STARTING reservation: a legend with many categories or long
# wrapped labels can render taller than this, so `_build_pie_figure` measures the
# legend's actual height and grows the reservation to match before it is final.
_PANEL_LEGEND_FRAC: float = 0.18
# Breathing room between the legend's top edge and the panels' `n = …` labels
# above it, as a fraction of the figure height.
_PANEL_LEGEND_GAP_FRAC: float = 0.025
# Gap between neighbouring panels, as a fraction of one panel's width. Pies have no
# axis furniture to keep apart, so this only has to stop two circles touching.
_PANEL_GAP_FRAC: float = 0.06


def _make_panel_axes(ctx, bg: str, n_panels: int):
    """A wide figure holding `n_panels` EQUAL square pie axes in one row, with room
    for a shared legend beneath them.

    Each axes is square and `set_aspect("equal")`, so every circle stays a circle;
    `place_picture_square` then scales the whole PNG on its limiting dimension and
    preserves that geometry in the slot.
    """
    register_fonts()
    w_in = max(9.0, ctx.slot.width / _EMU_PER_IN)
    h_in = max(4.5, ctx.slot.height / _EMU_PER_IN)
    fig = Figure(figsize=(w_in, h_in), dpi=200)
    FigureCanvasAgg(fig)
    fig.patch.set_facecolor(bg)

    bottom = _PANEL_LEGEND_FRAC
    height = 1.0 - bottom - 0.10          # 0.10 leaves room for the panel titles
    span = 1.0 / n_panels
    axes = []
    for i in range(n_panels):
        left = i * span + span * _PANEL_GAP_FRAC / 2.0
        width = span * (1.0 - _PANEL_GAP_FRAC)
        ax = fig.add_axes([left, bottom, width, height])
        ax.set_facecolor(bg)
        axes.append(ax)
    return fig, axes


def _legend_height_frac(fig, leg) -> float:
    """How tall `leg` actually rendered, as a fraction of the figure height.

    `_PANEL_LEGEND_FRAC` is only a starting guess — a legend with many categories
    (`ncol` wraps to more rows) or long wrapped labels can need more room than
    that. Forcing a draw lets matplotlib lay out the legend's real text extent so
    the reservation can be grown to fit it, rather than letting it overlap the
    panels above.
    """
    fig.canvas.draw()
    bbox = leg.get_window_extent(fig.canvas.get_renderer())
    return bbox.height / fig.bbox.height


def _add_category_legend(fig, ax, wedges, cats, statistic, fmt,
                          bg: str, ink: str, grid: str) -> None:
    """Add a house-style category legend to the right of the pie (no overlap, full text).
    Category names ONLY — the percentages live on the slices, so repeating them in the
    legend is redundant."""
    leg_labels = [_wrap_legend_label(c) for c in cats]
    leg = ax.legend(
        wedges, leg_labels,
        loc="center left", bbox_to_anchor=(1.02, 0.5),
        frameon=True, fontsize=10.5, labelspacing=0.8, handlelength=1.2,
        borderpad=0.8, handletextpad=0.7,
    )
    leg.get_frame().set_facecolor(bg)
    leg.get_frame().set_edgecolor(grid)
    leg.get_frame().set_linewidth(0.8)
    for t in leg.get_texts():
        t.set_color(ink)


def _draw_one_pie(ax, cats, vals, clrs, statistic, fmt, bg: str, donut: bool):
    """Draw a single pie onto `ax`. Returns its wedge artists."""
    total = sum(v or 0.0 for v in vals) or 1.0
    fracs = [(v or 0.0) / total * 100.0 for v in vals]

    def _autopct(pct: float) -> str:
        return format_value(pct, statistic, fmt, fracs) if pct >= _MIN_WEDGE_PCT else ""

    wedgeprops = dict(linewidth=1.4, edgecolor=bg)
    if donut:
        wedgeprops["width"] = 0.42

    wedges, _texts, autotexts = ax.pie(
        vals, labels=None, colors=clrs, autopct=_autopct,
        pctdistance=0.80 if donut else 0.72,
        startangle=90, counterclock=False, wedgeprops=wedgeprops,
    )
    ax.set_aspect("equal")
    for t, wedge in zip(autotexts, wedges):
        t.set_fontsize(10.0)
        t.set_fontweight("bold")
        t.set_color(contrast_ink(wedge.get_facecolor()))
    return wedges


def _build_pie_figure(ctx, *, donut: bool):
    """Build the figure for a pie/doughnut slide — one panel, or one per classifier
    group (spec 2026-08-22). Returns the Figure; placing it is the caller's job."""
    from matplotlib.patches import Patch

    series = ctx.series
    sel = panel_segments(series)
    cats = list(series.categories)
    clrs = series_colors(len(cats), palette=template_palette(ctx),
                          accent=chart_accent(ctx))
    clrs = [MUTED if c == NOT_ANSWERED_LABEL else clr for c, clr in zip(cats, clrs)]

    statistic = series.statistic
    fmt = ctx.spec.number_format
    bg = chart_background(ctx)
    ink, _muted, grid = chart_furniture(ctx)
    want_legend = bool(ctx.spec.elements.axis_names or ctx.spec.elements.legend)

    def _values(seg):
        return [float(series.cell(c, seg).value(statistic) or 0.0) for c in cats]

    if not sel.split or len(sel.labels) == 1:
        # One circle: the un-split slide, or a split that degraded to one panel.
        # Kept on the ORIGINAL layout (legend to the right) so existing slides do
        # not shift.
        fig, ax = _make_square_fig_ax(ctx, bg)
        seg = sel.labels[0]
        wedges = _draw_one_pie(ax, cats, _values(seg), clrs, statistic, fmt, bg, donut)
        if sel.split and not sel.degraded:
            # One group survived: the reader must be told WHICH group this is.
            ax.set_title(_wrap_legend_label(seg), fontsize=12.5, fontweight="bold",
                         color=ink, pad=6)
            ax.set_xlabel(f"n = {series.base_n.get(seg, 0)}", fontsize=9.5, color=ink)
        if want_legend:
            _add_category_legend(fig, ax, wedges, cats, statistic, fmt,
                                  bg, ink, grid)
        return fig

    fig, axes = _make_panel_axes(ctx, bg, len(sel.labels))
    for ax, seg in zip(axes, sel.labels):
        _draw_one_pie(ax, cats, _values(seg), clrs, statistic, fmt, bg, donut)
        ax.set_title(_wrap_legend_label(seg), fontsize=12.5, fontweight="bold",
                     color=ink, pad=6)
        ax.set_xlabel(f"n = {series.base_n.get(seg, 0)}", fontsize=9.5, color=ink)

    if want_legend:
        # ONE legend for the row: the categories are identical in every panel, so a
        # legend per panel would be the same list three times.
        handles = [Patch(facecolor=clrs[i], edgecolor="none") for i in range(len(cats))]
        leg = fig.legend(handles, [_wrap_legend_label(c) for c in cats],
                         loc="lower center", ncol=min(len(cats), 4),
                         frameon=True, fontsize=10.5, bbox_to_anchor=(0.5, 0.01))
        leg.get_frame().set_facecolor(bg)
        leg.get_frame().set_edgecolor(grid)
        leg.get_frame().set_linewidth(0.8)
        for t in leg.get_texts():
            t.set_color(ink)

        # A legend with many categories or long wrapped labels can render taller
        # than the fixed `_PANEL_LEGEND_FRAC` reservation `_make_panel_axes` used.
        # Measure it for real and, if it needs more room, shrink the panels
        # (keeping their top — and the titles above them — fixed) rather than let
        # the legend collide with the `n = …` labels or the circles.
        needed = _legend_height_frac(fig, leg) + _PANEL_LEGEND_GAP_FRAC
        if needed > _PANEL_LEGEND_FRAC:
            new_bottom = needed
            for ax in axes:
                left, _bottom, width, _height = ax.get_position().bounds
                top = 1.0 - 0.10  # same top the panels were given originally
                ax.set_position([left, new_bottom, width, top - new_bottom])
    return fig


def _render_pie(ctx, *, donut: bool) -> None:
    """Shared pie/doughnut renderer — circular, fully contained, labels never overlap."""
    place_picture_square(ctx, render_png(_build_pie_figure(ctx, donut=donut)))


def build_image_pie(ctx) -> None:
    """Single-series pie chart with house style (REQ-C-24b, REQ-C-27a).

    Uses the first segment's values.  Slices are coloured with the teal ramp;
    a category legend (with values) sits beside the circle so labels are always
    readable and never overlap.  The circle is rendered on a square axes and
    scaled to fit the slot preserving aspect ratio, so it is always circular and
    fully contained.  The "Not answered" slice is rendered in MUTED grey (R4.2).
    """
    _render_pie(ctx, donut=False)


def build_image_doughnut(ctx) -> None:
    """Single-series doughnut chart with house style (REQ-C-24b, REQ-C-27a).

    Pie with a central hole.  Slices use the teal ramp; a category legend (with
    values) sits beside the ring so labels are always readable and never overlap.
    Rendered circular and fully contained (see build_image_pie).  The "Not
    answered" slice is rendered in MUTED grey (R4.2).
    """
    _render_pie(ctx, donut=True)
