"""Image-mode funnel chart builder — nSight house style (REQ-C-24/25/27a).

Draws a TRUE funnel silhouette using centered horizontal bars (widest at top,
narrowest at bottom), which is only achievable in image mode.

House style:
- Slide-background bg, Liberation Sans font
- TEAL fill for all funnel stages
- White bold data labels centred in each bar (contrast against the fixed TEAL
  fill — unrelated to the slide background, so not slide-derived)
- Ink-tone category labels beside each bar (this IS on the slide background,
  and derived from it via `chart_furniture`)
- No x-axis (values are in labels); no spines
- No matplotlib title (handled by slide chrome, REQ-D-04)

Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values, format_value, wrap_label,
    chart_background, chart_furniture,
)
from reportbuilder.render.house_style import TEAL


def build_image_funnel(ctx) -> None:
    """Centered horizontal bar funnel (widest category on top) with house style.

    REQ-C-24b/f, REQ-C-27a.
    """
    cats, segs, data = series_values(ctx.series)
    vals = data[segs[0]]

    fig, ax = new_figure(ctx)
    bg = chart_background(ctx)
    ink, _muted, _grid = chart_furniture(ctx)

    max_val = max(vals) if vals else 1.0
    bar_h = 0.60
    all_vals = [v for v in vals if v is not None]

    for i, (cat, v) in enumerate(zip(cats, vals)):
        # Centre the bar on the x-axis (symmetric funnel silhouette)
        left = (max_val - v) / 2
        ax.barh(i, v, left=left, height=bar_h, color=TEAL, edgecolor=bg,
                linewidth=0.8, zorder=3)

        # Data label centred in bar — white on the fixed TEAL fill, same
        # reasoning as contrast_ink(TEAL), independent of the slide background.
        lbl = format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals)
        ax.text(
            left + v / 2, i, lbl,
            ha="center", va="center",
            fontsize=10.5, fontweight="bold", color="#FFFFFF",
            zorder=5,
        )

    # Category labels on the right of each bar — wrapped onto multiple lines
    # (and pathological long words force-broken) so they stay in a fixed gutter
    # instead of running off the slide.
    for i, cat in enumerate(cats):
        ax.text(
            max_val * 1.04, i, wrap_label(cat, 28),
            va="center", ha="left",
            fontsize=11.0, color=ink, zorder=5,
        )

    # Invert y-axis so widest bar (index 0) appears at the top
    ax.invert_yaxis()
    # Reserve a wide right gutter for the wrapped category labels.
    ax.set_xlim(0, max_val * 2.05)
    ax.axis("off")

    png = render_png(fig)
    place_picture(ctx, png)
