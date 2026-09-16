"""Image-mode combo chart builder — nSight house style (REQ-C-24/25/27a).

Renders bars on the primary y-axis (first segment) and a line on the secondary
y-axis via twinx (second segment). Falls back to bars-only if only 1 segment
is present.

House style:
- Slide-background bg, Liberation Sans
- First segment → TEAL bars; second segment → TEAL_LT line with circles
- Bottom spine; grid-tone gridlines; no top/right spines

Furniture (ink/muted/grid, bar/marker edges, legend frame) is derived from the
slide's own background via `chart_furniture`/`chart_background` — unchanged on
a light slide, flipped for legibility on a dark one.
- No matplotlib title (handled by slide chrome, REQ-D-04)

Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import VALUE_GID
from reportbuilder.render.image.label_fit import register_category_labels

from reportbuilder.render.image._mpl import (
    apply_axis_titles, new_figure, render_png, place_picture, series_values,
    format_value, chart_background, chart_furniture, colours_by_series,
    template_palette, chart_accent, series_label,
)
from reportbuilder.render.house_style import TEAL, TEAL_LT, series_colors
# Whether a clustered column has room for its number, measured rather than
# guessed from a segment count. Borrowed from the clustered bar builder rather
# than restated here: two answers to "does this number fit" is how one of them
# ends up wrong. (Johan, 2026-09-16)
from reportbuilder.render.image.bars import _value_label_layout


#: How each half of a combo may be drawn. "bar" and "line" are what the chart
#: always was; "area" is the same line with the ground filled under it.
COMBO_KINDS = ("bar", "line", "area")
PRIMARY_DEFAULT, SECONDARY_DEFAULT = "bar", "line"


def combo_kind(spec, key: str, fallback: str) -> str:
    """The shape one half of the combo is drawn in.

    Anything unrecognised falls back rather than drawing nothing: the value
    comes from a saved slide, so it can outlive the version that wrote it, and
    a blank chart is a worse answer than the default one.
    """
    value = (getattr(spec, "options", None) or {}).get(key)
    return value if value in COMBO_KINDS else fallback


def split_primary_and_secondary_segments(series, segs: list[str]) -> tuple[list[str], list[str]]:
    """(the question's own series, the secondary variable's series).

    The SECONDARY variable goes on the right-hand axis — it is a mean on its own
    scale, which is what that axis is for — and everything else on the left.
    With no secondary chosen there is no mean to find, and the chart falls back
    to what it has always done: the first series is the primary half and the
    rest are the secondary one.

    This names the two HALVES, not their shapes. What each is drawn as is
    `combo_primary_type` / `combo_secondary_type`.

    "The rest", not "the second". Reading exactly `segs[0]` and `segs[1]` meant a
    classifier with four groups drew two of them and discarded `Muu` and `En
    halua vastata` without a word. Whatever is handed here gets drawn.
    (Johan, 2026-09-16)
    """
    lines = [s for s in segs if series.statistic_of(s) == "mean"]
    if lines:
        return [s for s in segs if s not in lines], lines
    return list(segs[:1]), list(segs[1:])


def line_label_anchor(
    v: float, bar_v: float | None,
    bar_lim: tuple[float, float], line_lim: tuple[float, float],
    clearance_frac: float = 0.09,
) -> tuple[float, bool]:
    """Where a line point's own label goes: ``(y_on_line_axis, above)``.

    A combo chart's two series sit on different scales but share one pixel box,
    so a bar's height converts to the line's axis by proportion — no display
    round trip, and it holds whatever either axis is scaled to.

    The rule exists because a fixed side collides wherever the line crosses a
    bar, which is exactly where a reader is comparing them. Clearly above the
    bar's own label → above the marker. Otherwise below the BAR TOP, not merely
    below the marker: just over a bar, "under the marker" is precisely where
    that bar's label sits, which swaps one collision for another.

    And never so low that the label leaves the axes. The caller offsets it 9pt
    DOWNWARD from this anchor, and under the axes are the category labels and
    then the legend — so a point near the floor of the line's own scale had its
    number printed across both. Reported as "line label goes on top of the
    legend"; it is the same `3.0` that sits on `1- Ei lainkaan ylpeä`. The floor
    is one clearance above the axis bottom, the same distance the rule already
    uses to mean "a label's worth of room". (Johan, 2026-09-16)
    """
    a_lo, a_hi = bar_lim
    b_lo, b_hi = line_lim
    if bar_v is None or a_hi == a_lo:
        return v, True
    top_here = b_lo + (bar_v - a_lo) / (a_hi - a_lo) * (b_hi - b_lo)
    clearance = (b_hi - b_lo) * clearance_frac
    if v > top_here + clearance:
        return v, True
    return max(min(v, top_here - clearance), b_lo + clearance), False


def build_image_combo(ctx) -> None:
    """Combo chart: TEAL bars (primary y) + TEAL_LT line (secondary y via twinx).

    REQ-C-24b/f, REQ-C-27a.
    """
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    bg = chart_background(ctx)
    ink, muted, grid = chart_furniture(ctx)

    x = list(range(len(cats)))
    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    bar_segs, line_segs = split_primary_and_secondary_segments(ctx.series, segs)
    primary_kind = combo_kind(ctx.spec, "combo_primary_type", PRIMARY_DEFAULT)
    secondary_kind = combo_kind(ctx.spec, "combo_secondary_type", SECONDARY_DEFAULT)

    # Bar slots are allocated across BOTH halves at once. Each half is on its own
    # y-scale but they share one category slot on the x-axis, so two halves that
    # each took the whole slot would draw straight through each other — which is
    # what "bars on both axes" would otherwise look like.
    #
    # Bars fill 0.7 of the slot; the remaining 0.3 is the gap BETWEEN categories,
    # which is what keeps one category's cluster from touching the next. A lone
    # bar series keeps 0.8, so the ordinary two-variable combo is unchanged.
    bar_order = ((list(bar_segs) if primary_kind == "bar" else [])
                 + (list(line_segs) if secondary_kind == "bar" else []))
    n_bars = max(1, len(bar_order))
    span = 0.7 if n_bars > 1 else 0.8
    bar_w = span / n_bars

    def _slot(seg: str) -> list[float]:
        i = bar_order.index(seg)
        return [xi - span / 2 + bar_w * (i + 0.5) for xi in x]

    # Data labels. With several series the numbers share a category slot between
    # them, so the size (and whether they fit at all) is measured, not assumed —
    # the same rule the clustered bar builder uses.
    layout = (_value_label_layout(fig, ax, len(cats), bar_w,
                                  max((format_value(v, "pct", ctx.spec.number_format,
                                                    all_vals)
                                       for v in all_vals), key=len, default=""))
              if n_bars > 1 else (9.5, 0.0))

    def _draw_half(axes, seg_names: list[str], kind: str, *, lone_colour: str,
                   label_values: bool) -> list:
        """Draw one half of the combo in its chosen shape; return its artists."""
        n = max(1, len(seg_names))
        clrs = colours_by_series(
            series_colors(max(2, n), palette=template_palette(ctx),
                          accent=chart_accent(ctx)),
            list(seg_names), list(seg_names))
        out: list = []
        for i, seg in enumerate(seg_names):
            colour = lone_colour if n == 1 else clrs[i]
            # Named for the legend only when it cannot be identified otherwise:
            # a single primary series is the question itself, already in the
            # slide subtitle, so an entry for it just repeats the subtitle.
            #
            # Several primary series ARE the classifier's groups, so they state
            # their bases like every other chart's groups do — a combo split by
            # country otherwise named them where a clustered bar of the same
            # data would have said "Suomi (n=516)". The secondary half is a
            # VARIABLE, not a group, and has no base of its own to state.
            # (Johan, 2026-09-16)
            if n > 1 and axes is ax:
                name = series_label(ctx, seg)
            else:
                name = seg if axes is not ax else None
            if kind == "bar":
                out.append(axes.bar(
                    _slot(seg), data[seg], width=bar_w, color=colour,
                    edgecolor=bg, linewidth=0.8, zorder=3, label=name))
            else:
                if kind == "area":
                    axes.fill_between(
                        x, 0, [v if v is not None else 0.0 for v in data[seg]],
                        color=colour, alpha=0.25, linewidth=0, zorder=2)
                out.append(axes.plot(
                    x, data[seg], color=colour, marker="o", linewidth=2.2,
                    markersize=5, label=name, markeredgecolor=bg,
                    markeredgewidth=1.0, zorder=4)[0])
        # A line or an area has no bar to sit a number on, so its values are
        # placed above the point. Only when the half is a SINGLE series: several
        # lines put their labels in the same band and land on each other, and
        # there is no column width to measure a fit against the way bars have.
        # Without this, choosing "Line" silently cost the reader every number on
        # that half. (Johan, 2026-09-16)
        if kind != "bar" and label_values and len(seg_names) == 1:
            seg = seg_names[0]
            vals = [v for v in data[seg] if v is not None]
            for xi, v in zip(x, data[seg]):
                if v is None:
                    continue
                axes.annotate(
                    format_value(v, ctx.series.statistic_of(seg),
                                 ctx.spec.number_format, vals),
                    xy=(xi, v), xytext=(0, 9), textcoords="offset points",
                    ha="center", va="bottom", fontsize=9.5, fontweight="bold",
                    color=ink, zorder=6, gid=VALUE_GID,
                    bbox={"boxstyle": "round,pad=0.18", "facecolor": bg,
                          "edgecolor": "none", "alpha": 0.85},
                )
        if kind == "bar" and label_values and layout:
            value_fs, rot = layout
            for seg, bars in zip(seg_names, out):
                for bar, v in zip(bars, data[seg]):
                    if v is None:
                        continue
                    axes.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_height() + max(0.5, bar.get_height() * 0.01),
                        format_value(v, ctx.series.statistic_of(seg),
                                     ctx.spec.number_format, all_vals),
                        ha="center", va="bottom", rotation=rot,
                        fontsize=value_fs, fontweight="bold", color=ink, zorder=5,
                        gid=VALUE_GID,
                    )
        return out

    _draw_half(ax, list(bar_segs), primary_kind, lone_colour=TEAL,
               label_values=True)

    # House-style spines for primary axis
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)
    ax.tick_params(axis="both", length=0)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=11.5, color=ink)
    register_category_labels(ax, "x", cats)
    ax.yaxis.set_tick_params(labelcolor=muted, labelsize=9.5)

    # Grid-tone gridlines
    max_bar = max((v for seg in bar_segs for v in data[seg] if v is not None),
                  default=0.0)
    for yv in [20, 40, 60, 80, 100]:
        if yv <= max_bar * 1.20:
            ax.axhline(yv, color=grid, lw=0.8, zorder=1)

    if line_segs:
        ax2 = ax.twinx()
        # Only bars label themselves here. Drawn as a line or an area, the
        # secondary half's numbers are placed by the anchored rule below, which
        # dodges the bars underneath them — letting both run would print every
        # number twice.
        _draw_half(ax2, list(line_segs), secondary_kind, lone_colour=TEAL_LT,
                   label_values=(secondary_kind == "bar"))

        # The line's own values. Without them the bars are labelled and the line
        # is not, so the only way to read it is off the right-hand axis — on the
        # one chart type whose whole point is that the two series are on
        # DIFFERENT scales. The spec asks for the numeric values of the classes.
        #
        # Only ONE line is labelled — the numbers are placed against the bar
        # under them, and several lines' labels in one band land on each other.
        # With a secondary variable there is exactly one line anyway; the
        # many-line case is the no-secondary fallback, where the right-hand axis
        # and the legend carry it.
        #
        # Drawn as BARS, the secondary half labels its own bars inside
        # `_draw_half` like any bar series, so this anchored placement — which
        # exists to dodge the bars underneath a line — does not apply.
        labelled = (line_segs[0]
                    if len(line_segs) == 1 and secondary_kind != "bar" else None)
        line_vals = [v for seg in line_segs for v in data[seg] if v is not None]
        if line_vals:
            # Headroom for a label at either extreme. They are drawn in offset
            # POINTS, so matplotlib's autoscaling never sees them and a peak at
            # the end of the series puts its own value outside the figure.
            lo, hi = min(line_vals), max(line_vals)
            span = (hi - lo) or (abs(hi) or 1.0)
            ax2.set_ylim(lo - span * 0.16, hi + span * 0.16)

        # Which side of the marker the label goes. The line crosses the bars, so
        # a fixed side collides with the bar's own label wherever the two meet —
        # which is exactly where a reader is trying to compare them.
        #
        # Both axes share one pixel box, so a bar's height converts to the line
        # axis by proportion. No display-coordinate round trip, and it holds
        # whatever either axis is scaled to.
        bar_lim, line_lim = ax.get_ylim(), ax2.get_ylim()
        # The tallest bar in each category is what a line label has to clear —
        # with a cluster under it, dodging only the first series' bar puts the
        # number straight onto a taller neighbour.
        tallest = [max((data[s][i] for s in bar_segs if data[s][i] is not None),
                       default=None)
                   for i in range(len(cats))]
        for xi, v, bar_v in zip(x, data[labelled] if labelled else [], tallest):
            if v is None:
                continue
            y, above = line_label_anchor(v, bar_v, bar_lim, line_lim)
            ax2.annotate(
                # The line's OWN statistic. On a two-variable combo it is the
                # mean of another variable — a 1-8 index, not a percentage —
                # and the two segments cannot share one format. (2026-09-16)
                format_value(v, ctx.series.statistic_of(labelled),
                             ctx.spec.number_format, line_vals),
                xy=(xi, y), xytext=(0, 9 if above else -9),
                textcoords="offset points",
                ha="center", va="bottom" if above else "top",
                fontsize=9.5, fontweight="bold", color=ink, zorder=6,
                gid=VALUE_GID,
                # The line crosses the bars; a bare number over a dark bar is
                # unreadable.
                bbox={"boxstyle": "round,pad=0.18", "facecolor": bg,
                      "edgecolor": "none", "alpha": 0.85},
            )

        for spine in ax2.spines.values():
            spine.set_visible(False)
        ax2.spines["right"].set_visible(True)
        ax2.spines["right"].set_color("#C9C1B4")
        ax2.spines["right"].set_linewidth(1.0)
        ax2.yaxis.set_tick_params(labelcolor=muted, labelsize=9.5)

        if ctx.spec.elements.legend:
            # The line always, because the reader cannot otherwise tell what it
            # is. The BARS only when there are several — one bar series is the
            # question itself, already named in the slide subtitle, so an entry
            # for it just repeats the subtitle; several are the classifier's
            # groups, and nothing else on the chart names them.
            #
            # Style the frame in place; style_legend() would rebuild the legend
            # from the bar axis and lose the line.
            handles1, labels1 = ax.get_legend_handles_labels()
            handles2, labels2 = ax2.get_legend_handles_labels()
            handles, labels = handles1 + handles2, labels1 + labels2
            if labels:
                # BELOW the axes, like radar and the grouped bars. "best" put it
                # inside the plot, where on a rising line it landed on top of the
                # last marker and its value — matplotlib picks the emptiest
                # corner, and on this chart the emptiest corner is still data.
                leg = ax.legend(handles, labels, fontsize=9.5, frameon=True,
                                loc="upper center", bbox_to_anchor=(0.5, -0.08),
                                ncol=min(len(labels), 5), borderaxespad=0.0)
                leg.get_frame().set_facecolor(bg)
                leg.get_frame().set_edgecolor(grid)
                leg.get_frame().set_linewidth(0.8)
                for t in leg.get_texts():
                    t.set_color(ink)
    # Bars-only combo (no secondary line) → no legend: the question is in the subtitle.

    # On the PRIMARY axis. The secondary axis is the line's own scale and is
    # named by the legend entry that describes the line.
    apply_axis_titles(ax, ctx.spec, ink)

    png = render_png(fig)
    place_picture(ctx, png)
