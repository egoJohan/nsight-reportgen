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

With a classifying variable, one funnel per group side by side — the same panel
rule the pie uses (spec 2026-08-22).

Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image._mpl import (
    new_figure, new_figure_grid, render_png, place_picture, format_value, wrap_label,
    chart_background, chart_furniture,
)
from reportbuilder.render.house_style import TEAL
from reportbuilder.render.panels import panel_segments


def _draw_one_funnel(ax, cats, vals, ctx, bg: str, ink: str) -> None:
    """Draw one funnel silhouette onto `ax` — the body this module always had."""
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


def build_image_funnel(ctx) -> None:
    """Centered horizontal bar funnel (widest category on top) with house style.

    With a classifying variable, one funnel per group side by side — the same
    panel rule the pie uses. (REQ-C-24b/f, REQ-C-27a; spec 2026-08-22)
    """
    sel = panel_segments(ctx.series)
    cats = list(ctx.series.categories)
    bg = chart_background(ctx)
    ink, _muted, _grid = chart_furniture(ctx)

    def _values(seg):
        return [float(ctx.series.cell(c, seg).value(ctx.series.statistic) or 0.0)
                for c in cats]

    def _label(seg) -> str:
        # `ax.axis("off")` hides the x-axis label, so the base rides in the title's
        # second line rather than under the funnel as it does on a pie.
        return f"{wrap_label(seg, 20)}\nn = {ctx.series.base_n.get(seg, 0)}"

    if not sel.split or len(sel.labels) == 1:
        fig, ax = new_figure(ctx)
        seg = sel.labels[0]
        _draw_one_funnel(ax, cats, _values(seg), ctx, bg, ink)
        if sel.split and not sel.degraded:
            # One group survived: the reader must be told WHICH group this is.
            ax.set_title(_label(seg), fontsize=12.5, fontweight="bold",
                         color=ink, pad=6)
    else:
        # Every panel draws the same categories, so the shared y-axis is correct.
        fig, axes = new_figure_grid(ctx, len(sel.labels))
        for ax, seg in zip(axes, sel.labels):
            _draw_one_funnel(ax, cats, _values(seg), ctx, bg, ink)
            ax.set_title(_label(seg), fontsize=12.5, fontweight="bold",
                         color=ink, pad=6)

    place_picture(ctx, render_png(fig))
