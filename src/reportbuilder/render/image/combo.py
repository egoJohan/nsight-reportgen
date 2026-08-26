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

from reportbuilder.render.image._mpl import (
    apply_axis_titles, new_figure, render_png, place_picture, series_values,
    format_value, chart_background, chart_furniture,
)
from reportbuilder.render.house_style import TEAL, TEAL_LT


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
    """
    a_lo, a_hi = bar_lim
    b_lo, b_hi = line_lim
    if bar_v is None or a_hi == a_lo:
        return v, True
    top_here = b_lo + (bar_v - a_lo) / (a_hi - a_lo) * (b_hi - b_lo)
    clearance = (b_hi - b_lo) * clearance_frac
    if v > top_here + clearance:
        return v, True
    return min(v, top_here - clearance), False


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

    # Primary bars (segment 0 → TEAL). NOT labelled for the legend: the bar series is
    # the question itself, whose text already sits in the slide's subtitle — a legend
    # entry just repeats it. The legend keeps only the LINE (the secondary variable),
    # which the reader can't otherwise identify.
    bars = ax.bar(x, data[segs[0]], color=TEAL, edgecolor=bg,
                  linewidth=0.8, zorder=3)

    # Data labels on bars
    for bar, v in zip(bars, data[segs[0]]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(0.5, bar.get_height() * 0.01),
            format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
            ha="center", va="bottom",
            fontsize=9.5, fontweight="bold", color=ink, zorder=5,
        )

    # House-style spines for primary axis
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)
    ax.tick_params(axis="both", length=0)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=11.5, color=ink)
    ax.yaxis.set_tick_params(labelcolor=muted, labelsize=9.5)

    # Grid-tone gridlines
    all_bar_vals = data[segs[0]]
    max_bar = max(all_bar_vals, default=0.0)
    for yv in [20, 40, 60, 80, 100]:
        if yv <= max_bar * 1.20:
            ax.axhline(yv, color=grid, lw=0.8, zorder=1)

    if len(segs) >= 2:
        # Secondary line (segment 1 → TEAL_LT)
        ax2 = ax.twinx()
        ax2.plot(x, data[segs[1]], color=TEAL_LT, marker="o",
                 linewidth=2.2, markersize=5, label=segs[1],
                 markeredgecolor=bg, markeredgewidth=1.0, zorder=4)

        # The line's own values. Without them the bars are labelled and the line
        # is not, so the only way to read it is off the right-hand axis — on the
        # one chart type whose whole point is that the two series are on
        # DIFFERENT scales. The spec asks for the numeric values of the classes.
        line_vals = [v for v in data[segs[1]] if v is not None]
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
        for xi, v, bar_v in zip(x, data[segs[1]], data[segs[0]]):
            if v is None:
                continue
            y, above = line_label_anchor(v, bar_v, bar_lim, line_lim)
            ax2.annotate(
                format_value(v, ctx.series.statistic, ctx.spec.number_format,
                             line_vals),
                xy=(xi, y), xytext=(0, 9 if above else -9),
                textcoords="offset points",
                ha="center", va="bottom" if above else "top",
                fontsize=9.5, fontweight="bold", color=ink, zorder=6,
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
            # Legend shows ONLY the line (the secondary variable) — the bars are the
            # question itself, already named in the slide subtitle, so a bar entry just
            # repeats it. Style the frame in place; style_legend() would rebuild the
            # legend from the bar axis and lose the line.
            lines2, labels2 = ax2.get_legend_handles_labels()
            if labels2:
                # BELOW the axes, like radar and the grouped bars. "best" put it
                # inside the plot, where on a rising line it landed on top of the
                # last marker and its value — matplotlib picks the emptiest
                # corner, and on this chart the emptiest corner is still data.
                leg = ax.legend(lines2, labels2, fontsize=9.5, frameon=True,
                                loc="upper center", bbox_to_anchor=(0.5, -0.08),
                                ncol=1, borderaxespad=0.0)
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
