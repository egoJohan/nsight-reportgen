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


# X-range each panel reserves, as a multiple of the SHARED bar scale. A panel that
# draws the stage labels needs the wide right gutter the funnel always had; one
# that does not can hand most of it back to the funnel (a small margin still
# absorbs a value label pushed just outside a narrow bar). The grid gives each
# panel a width in the same proportion, so a data unit is the same number of
# pixels in every panel — which is what makes the bar widths comparable.
_GUTTER_WITH_LABELS = 2.05
_GUTTER_BARE = 1.20


def _draw_one_funnel(ax, cats, vals, ctx, bg: str, ink: str, *,
                     scale_max: float | None = None,
                     stage_labels: bool = True) -> None:
    """Draw one funnel silhouette onto `ax` — the body this module always had.

    `scale_max` is the bar scale SHARED by every panel in the row: a funnel reads
    magnitude, so a group running 90/60/30 and one running 45/30/15 must not draw
    identical silhouettes. Left at None (the un-split slide) it is this panel's
    own maximum — exactly what this function always used.

    `stage_labels` draws the category names in the right gutter. Only ONE panel
    per row does (the rightmost), so long scale labels are not repeated three
    times across a row that has a third of the width to spare.
    """
    max_val = float(scale_max) if scale_max is not None else (
        max(vals) if vals else 1.0)
    max_val = max_val or 1.0
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
    # instead of running off the slide. In a panel row only the rightmost panel
    # carries them, so they sit at the row's right edge the way they sit at the
    # un-split funnel's right edge.
    if stage_labels:
        for i, cat in enumerate(cats):
            ax.text(
                max_val * 1.04, i, wrap_label(cat, 28),
                va="center", ha="left",
                fontsize=11.0, color=ink, zorder=5,
            )

    # Widest bar (index 0) at the TOP. `invert_yaxis()` TOGGLES the axis, and a
    # panel grid SHARES one y-axis (`new_figure_grid(..., sharey=True)`), so
    # calling it once per panel cancelled itself on an even panel count — a
    # two-group funnel (the likeliest split of all: by gender) drew the narrowest
    # stage on top. Re-stating the limits in descending order is idempotent: the
    # same call on every panel leaves the same orientation whatever the panel
    # count. Derived from the autoscaled range rather than hard-coded to
    # (n - 0.5, -0.5) so the un-split funnel keeps its exact bar margins.
    lo, hi = sorted(ax.get_ylim())
    ax.set_ylim(hi, lo)
    # Reserve a right gutter — wide when this panel carries the wrapped category
    # labels, narrow when it does not (the funnel reclaims that width).
    ax.set_xlim(0, max_val * (_GUTTER_WITH_LABELS if stage_labels
                              else _GUTTER_BARE))
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
        # ONE bar scale for the whole row. A funnel reads MAGNITUDE, so panels
        # that each rescaled to their own maximum drew 90/60/30 and 45/30/15 as
        # identical silhouettes — defeating the very comparison the split exists
        # to make. The scale is the largest value across the drawn panels; with a
        # single panel it is that panel's own maximum, i.e. unchanged.
        panel_vals = [_values(seg) for seg in sel.labels]
        scale_max = max((max(v) for v in panel_vals if v), default=1.0)

        # Only the RIGHTMOST panel carries the stage labels (see
        # `_draw_one_funnel`), so it is the only one that needs the wide label
        # gutter. Widths in the same ratio as the x-ranges keep a data unit worth
        # the same number of pixels in every panel — without that, the labelled
        # panel would draw a visibly smaller funnel than its neighbours and the
        # shared scale would buy nothing.
        n = len(sel.labels)
        ratios = [_GUTTER_BARE] * (n - 1) + [_GUTTER_WITH_LABELS]
        fig, axes = new_figure_grid(ctx, n, width_ratios=ratios)
        for i, (ax, seg) in enumerate(zip(axes, sel.labels)):
            gutter = _GUTTER_WITH_LABELS if i == n - 1 else _GUTTER_BARE
            _draw_one_funnel(ax, cats, panel_vals[i], ctx, bg, ink,
                             scale_max=scale_max, stage_labels=(i == n - 1))
            # The funnel is centred on `scale_max / 2`, not on the axes, so the
            # group name goes over the FUNNEL rather than over the label gutter
            # it shares the panel with.
            ax.set_title(_label(seg), fontsize=12.5, fontweight="bold",
                         color=ink, pad=6, x=0.5 / gutter)

    place_picture(ctx, render_png(fig))
