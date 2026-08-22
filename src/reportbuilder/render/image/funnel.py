"""Image-mode funnel chart builder — nSight house style (REQ-C-24/25/27a).

Draws a TRUE funnel silhouette using centered horizontal bars (widest at top,
narrowest at bottom), which is only achievable in image mode.

House style:
- Slide-background bg, Liberation Sans font
- TEAL fill for all funnel stages
- White bold data labels centred in each bar (contrast against the fixed TEAL
  fill — unrelated to the slide background, so not slide-derived); a label too
  wide for its own bar (a narrow stage in a narrow panel) is instead placed just
  right of the bar in ink tone, never shrunk and never left illegible-white
  outside the fill it was sized for
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

    value_labels = []  # (Text, left, v, i) — fitted against the real bar width below
    for i, (cat, v) in enumerate(zip(cats, vals)):
        # Centre the bar on the x-axis (symmetric funnel silhouette)
        left = (max_val - v) / 2
        ax.barh(i, v, left=left, height=bar_h, color=TEAL, edgecolor=bg,
                linewidth=0.8, zorder=3)

        # Data label centred in bar — white on the fixed TEAL fill, same
        # reasoning as contrast_ink(TEAL), independent of the slide background.
        lbl = format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals)
        text = ax.text(
            left + v / 2, i, lbl,
            ha="center", va="center",
            fontsize=10.5, fontweight="bold", color="#FFFFFF",
            zorder=5,
        )
        value_labels.append((text, left, v, i))

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

    _fit_value_labels(ax, value_labels, max_val, ink)


def _fit_value_labels(ax, value_labels, max_val: float, ink: str) -> None:
    """Move a value label outside its bar, in ink instead of white, when it does
    not fit inside the bar's own rendered width.

    A panel row (spec 2026-08-22) can draw a funnel at a THIRD of the width a
    funnel was ever drawn at before this feature — a narrow stage's white label,
    centred and sized exactly as always, can now overflow the bar onto the light
    background behind it, where white-on-white is unreadable (a reader can misread
    "20 %" as "0 %"). A label that already fits inside its bar is untouched: same
    position, same colour, same size, byte-identical to the funnel this module
    always drew.

    Measured with matplotlib's own text metrics (`Text.get_window_extent` after a
    forced `draw()`) against the bar's true on-screen width via `ax.transData` —
    the same "measure the real render, don't estimate" technique
    `_legend_height_frac` (image/pie.py) uses on this same kind of already-built,
    correctly-sized figure.
    """
    if not value_labels:
        return
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    gap = max_val * 0.02
    for text, left, v, i in value_labels:
        x0_px, _ = ax.transData.transform((left, i))
        x1_px, _ = ax.transData.transform((left + v, i))
        bar_px = abs(x1_px - x0_px)
        if text.get_window_extent(renderer).width > bar_px:
            text.set_position((left + v + gap, i))
            text.set_ha("left")
            text.set_color(ink)


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
