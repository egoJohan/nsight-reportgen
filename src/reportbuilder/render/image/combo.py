"""Image-mode combo chart builder — nSight house style (REQ-C-24/25/27a).

Renders bars on the primary y-axis (first segment) and a line on the secondary
y-axis via twinx (second segment). Falls back to bars-only if only 1 segment
is present.

House style:
- Cream bg, Liberation Sans
- First segment → TEAL bars; second segment → TEAL_LT line with circles
- Bottom spine; GRIDC gridlines; no top/right spines
- No matplotlib title (handled by slide chrome, REQ-D-04)

Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values,
    fmt_value, style_legend,
)
from reportbuilder.render.house_style import TEAL, TEAL_LT, INK, MUTED, GRIDC, CREAM


def build_image_combo(ctx) -> None:
    """Combo chart: TEAL bars (primary y) + TEAL_LT line (secondary y via twinx).

    REQ-C-24b/f, REQ-C-27a.
    """
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)

    x = list(range(len(cats)))

    # Primary bars (segment 0 → TEAL)
    bars = ax.bar(x, data[segs[0]], color=TEAL, edgecolor=CREAM,
                  linewidth=0.8, label=segs[0], zorder=3)

    # Data labels on bars
    for bar, v in zip(bars, data[segs[0]]):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + max(0.5, bar.get_height() * 0.01),
            fmt_value(v, ctx.series.statistic, ctx.spec.number_format),
            ha="center", va="bottom",
            fontsize=9.5, fontweight="bold", color=INK, zorder=5,
        )

    # House-style spines for primary axis
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)
    ax.tick_params(axis="both", length=0)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=11.5, color=INK)
    ax.yaxis.set_tick_params(labelcolor=MUTED, labelsize=9.5)

    # GRIDC gridlines
    all_bar_vals = data[segs[0]]
    max_bar = max(all_bar_vals, default=0.0)
    for yv in [20, 40, 60, 80, 100]:
        if yv <= max_bar * 1.20:
            ax.axhline(yv, color=GRIDC, lw=0.8, zorder=1)

    if len(segs) >= 2:
        # Secondary line (segment 1 → TEAL_LT)
        ax2 = ax.twinx()
        ax2.plot(x, data[segs[1]], color=TEAL_LT, marker="o",
                 linewidth=2.2, markersize=5, label=segs[1],
                 markeredgecolor=CREAM, markeredgewidth=1.0, zorder=4)
        for spine in ax2.spines.values():
            spine.set_visible(False)
        ax2.spines["right"].set_visible(True)
        ax2.spines["right"].set_color("#C9C1B4")
        ax2.spines["right"].set_linewidth(1.0)
        ax2.yaxis.set_tick_params(labelcolor=MUTED, labelsize=9.5)

        if ctx.spec.elements.legend:
            lines1, labels1 = ax.get_legend_handles_labels()
            lines2, labels2 = ax2.get_legend_handles_labels()
            ax.legend(lines1 + lines2, labels1 + labels2,
                      fontsize=9.5, frameon=True, loc="best")
            style_legend(ax, loc="best")
    else:
        if ctx.spec.elements.legend:
            style_legend(ax, loc="best")

    png = render_png(fig)
    place_picture(ctx, png)
