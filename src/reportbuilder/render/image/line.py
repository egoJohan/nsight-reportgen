"""Image-mode line chart builder — nSight house style (REQ-C-24/25/27a).

Builder: build_image_line — one line per segment with house-styled spines,
GRIDC gridlines, teal-ramp colours, INK data labels, and no title in the axes
(title lives in slide chrome, REQ-D-04).
Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values,
    format_value, style_legend, wrap_label,
)
from reportbuilder.render.house_style import (
    series_colors, INK, MUTED, GRIDC, CREAM,
)


def build_image_line(ctx) -> None:
    """Line chart: one line per segment, x-axis = categories (REQ-C-24b/f, REQ-C-27a).

    House style:
    - Cream bg, Liberation Sans, teal ramp per segment
    - INK bold data labels above each point (always shown)
    - Bottom spine only (light), GRIDC horizontal gridlines at 20-unit intervals
    - No matplotlib title (handled by slide chrome, REQ-D-04)
    """
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    clrs = series_colors(len(segs))

    x = list(range(len(cats)))

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=100.0)

    for i, seg in enumerate(segs):
        vals = data[seg]
        ax.plot(
            x, vals,
            marker="o", label=seg, color=clrs[i],
            linewidth=2.5, markersize=6,
            markeredgecolor=CREAM, markeredgewidth=1.2,
            zorder=3,
        )
        # Data labels always shown (INK bold, above each point)
        for xi, v in zip(x, vals):
            if v is not None:
                ax.annotate(
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    xy=(xi, v),
                    xytext=(0, 7),
                    textcoords="offset points",
                    ha="center", va="bottom",
                    fontsize=9.5, fontweight="bold", color=INK, zorder=5,
                )

    # Category labels — wrapped (and pathological long words force-broken), and
    # rotated when there are several long labels so they don't overlap/run off.
    wrapped = [wrap_label(c, 16) for c in cats]
    longest = max((len(c) for c in cats), default=0)
    rotate = len(cats) > 4 or longest > 16
    ax.set_xticks(x)
    ax.set_xticklabels(
        wrapped, fontsize=10.5 if rotate else 11.5, color=INK,
        rotation=25 if rotate else 0,
        ha="right" if rotate else "center",
        rotation_mode="anchor" if rotate else None,
    )
    ax.tick_params(axis="both", length=0)

    # House-style spines: bottom spine only
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)

    # GRIDC horizontal gridlines
    ax_max = min(100.0, max(max_val * 1.20, 10.0))
    for yv in [20, 40, 60, 80, 100]:
        if yv <= ax_max:
            ax.axhline(yv, color=GRIDC, lw=0.8, zorder=1)

    y_ticks = [v for v in [0, 20, 40, 60, 80, 100] if v <= ax_max]
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([str(v) for v in y_ticks], fontsize=9.5, color=MUTED)
    ax.set_ylim(0, ax_max)

    if ctx.spec.elements.legend and len(segs) > 1:
        style_legend(ax, loc="best")

    png = render_png(fig)
    place_picture(ctx, png)
