"""Image-mode pie and doughnut chart builders — nSight house style (REQ-C-24/25/27a).

Builders: build_image_pie, build_image_doughnut.

House style:
- Cream figure background, Liberation Sans font
- Teal ramp for slice colours (single series → TEAL, multi-slice → spread)
- Percentage labels on slices that are large enough; a category legend (with the
  value) sits beside the pie so labels are ALWAYS readable and NEVER overlap,
  even when several slices are tiny / near-zero.
- No matplotlib title (handled by slide chrome, REQ-D-04)
- Only suitable for single-choice parts-of-whole questions

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

from reportbuilder.render.image._mpl import (
    render_png, place_picture_square, series_values, format_value,
)
from reportbuilder.render.house_style import (
    register_fonts, series_colors, INK, MUTED, CREAM, GRIDC,
)
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL

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


def _make_square_fig_ax(ctx):
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
    fig.patch.set_facecolor(CREAM)
    # Pie axes: left ~62% of the width, full height — the circle fills the height.
    ax = fig.add_axes([0.0, 0.0, 0.62, 1.0])
    ax.set_facecolor(CREAM)
    return fig, ax


def _add_category_legend(fig, ax, wedges, cats, fracs, statistic, fmt) -> None:
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
    leg.get_frame().set_facecolor(CREAM)
    leg.get_frame().set_edgecolor(GRIDC)
    leg.get_frame().set_linewidth(0.8)
    for t in leg.get_texts():
        t.set_color(INK)


def _render_pie(ctx, *, donut: bool) -> None:
    """Shared pie/doughnut renderer — circular, fully contained, labels never overlap."""
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]
    clrs = series_colors(len(cats))
    # R4.2: override "Not answered" slice colour with MUTED grey.
    clrs = [MUTED if c == NOT_ANSWERED_LABEL else clr for c, clr in zip(cats, clrs)]

    statistic = ctx.series.statistic
    fmt = ctx.spec.number_format
    total = sum(v or 0.0 for v in vals) or 1.0
    fracs = [(v or 0.0) / total * 100.0 for v in vals]

    fig, ax = _make_square_fig_ax(ctx)

    def _autopct(pct: float) -> str:
        # Only annotate slices large enough to hold the label cleanly; tiny/zero
        # slices would otherwise overlap their neighbours' text.  Every value is
        # still shown in the legend.
        return format_value(pct, statistic, fmt, fracs) if pct >= _MIN_WEDGE_PCT else ""

    wedgeprops = dict(linewidth=1.4, edgecolor=CREAM)
    if donut:
        wedgeprops["width"] = 0.42

    wedges, texts, autotexts = ax.pie(
        vals,
        labels=None,                 # category names go in the legend (never overlap)
        colors=clrs,
        autopct=_autopct,
        pctdistance=0.80 if donut else 0.72,
        startangle=90,
        counterclock=False,
        wedgeprops=wedgeprops,
    )
    ax.set_aspect("equal")

    for t in autotexts:
        t.set_fontsize(10.0)
        t.set_fontweight("bold")
        t.set_color(INK)

    if ctx.spec.elements.axis_names or ctx.spec.elements.legend:
        _add_category_legend(fig, ax, wedges, cats, fracs, statistic, fmt)

    png = render_png(fig)
    place_picture_square(ctx, png)


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
