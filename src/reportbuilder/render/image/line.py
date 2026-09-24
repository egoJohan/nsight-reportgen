"""Image-mode line chart builder — nSight house style (REQ-C-24/25/27a).

Builder: build_image_line — one line per segment with house-styled spines,
grid-tone gridlines, teal-ramp colours, ink-tone data labels, and no title in
the axes (title lives in slide chrome, REQ-D-04).

Furniture (ink/muted/grid, marker edges, axes background) is derived from the
slide's own background via `chart_furniture`/`chart_background` — INK/MUTED/
GRIDC/CREAM unchanged on a light slide, flipped for legibility on a dark one.
Returns None.
"""
from __future__ import annotations

from reportbuilder.render.image.bars import _category_ticks, _as_one_series_per_group
from reportbuilder.render.image._mpl import (apply_axis_titles, chart_accent,
    chart_background,
    chart_furniture, new_figure, render_png, place_picture, series_values,
    format_value, series_label, style_legend, wrap_label, place_total,
    colours_by_series, coded_order, _value_axis, author_label_floor,
)
from reportbuilder.render.house_style import series_colors
from reportbuilder.render.image._mpl import template_palette
from reportbuilder.render.image._mpl import VALUE_GID
from reportbuilder.render.image.label_fit import register_category_labels



def _tick_text(v: float) -> str:
    """A tick label without a pointless ".0" — counts are whole numbers, and a
    mean's ticks may not be."""
    return str(int(v)) if float(v).is_integer() else f"{v:g}"

def build_image_line(ctx) -> None:
    """Line chart: one line per segment, x-axis = categories (REQ-C-24b/f, REQ-C-27a).

    House style:
    - Slide-background bg, Liberation Sans, teal ramp per segment
    - Ink-tone bold data labels above each point (always shown)
    - Bottom spine only (light), grid-tone horizontal gridlines at 20-unit intervals
    - No matplotlib title (handled by slide chrome, REQ-D-04)
    """
    cats, segs, data = series_values(ctx.series)
    # A summary statistic is ONE category (the question) times the groups,
    # which drawn literally is every group's point stacked on one x. The bar
    # builder already transposes it — see `_as_one_series_per_group` — and
    # this did not. (Johan, 2026-09-16)
    cats, segs, data = _as_one_series_per_group(ctx, cats, segs, data)
    # A line has no top or bottom; its legend has a first and a last.
    default_segs, segs = coded_order(ctx.series, segs), place_total(segs, getattr(ctx.spec, "total_position", "auto"))
    fig, ax = new_figure(ctx)
    bg = chart_background(ctx)
    ink, muted, grid = chart_furniture(ctx)
    clrs = colours_by_series(series_colors(len(segs), palette=template_palette(ctx),
                                           accent=chart_accent(ctx)),
                             default_segs, segs)

    x = list(range(len(cats)))

    all_vals = [v for seg in segs for v in data[seg] if v is not None]
    max_val = max(all_vals, default=100.0)

    for i, seg in enumerate(segs):
        vals = data[seg]
        ax.plot(
            x, vals,
            marker="o", label=series_label(ctx, seg), color=clrs[i],
            linewidth=2.5, markersize=6,
            markeredgecolor=bg, markeredgewidth=1.2,
            zorder=3,
        )
        # Data labels above each point, ink-tone bold — except any the author
        # asked not to print (`number_format.hide_below_pct`).
        _floor = author_label_floor(ctx.spec, ctx.series.statistic, all_vals)
        for xi, v in zip(x, vals):
            if v is not None and v >= _floor:
                ax.annotate(
                    format_value(v, ctx.series.statistic, ctx.spec.number_format, all_vals),
                    xy=(xi, v),
                    xytext=(0, 7),
                    textcoords="offset points",
                    ha="center", va="bottom",
                    fontsize=9.5, fontweight="bold", color=ink, zorder=5,
                    gid=VALUE_GID,
                )

    # Category labels — wrapped (and pathological long words force-broken), and
    # rotated when there are several long labels so they don't overlap/run off.
    wrapped = [wrap_label(c, 16) for c in cats]
    longest = max((len(c) for c in cats), default=0)
    rotate = len(cats) > 4 or longest > 16
    ax.set_xticks(x)
    # Through the shared rule: a lone SUMMARY category is the question itself,
    # and printing it under the axis repeats the subtitle as an axis title
    # nobody asked for. See `_category_ticks`. (Johan, 2026-09-16)
    ax.set_xticklabels(
        _category_ticks(wrapped, lambda t: t, ctx.series.statistic),
        fontsize=10.5 if rotate else 11.5, color=ink,
        rotation=25 if rotate else 0,
        ha="right" if rotate else "center",
        rotation_mode="anchor" if rotate else None,
    )
    register_category_labels(ax, "x", cats, wrap=wrap_label, width=16)
    ax.tick_params(axis="both", length=0)

    # House-style spines: bottom spine only
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.spines["bottom"].set_visible(True)
    ax.spines["bottom"].set_color("#C9C1B4")
    ax.spines["bottom"].set_linewidth(1.0)

    # The shared axis rule. This used to be a copy of the PERCENTAGE half of it
    # — `min(100.0, …)` — applied to every statistic, so a line of counts ran
    # off the top of its own chart and its points were drawn outside the axes.
    # ("Jos line chartissa tunnusluvuksi valitsee count, niin kuvaaja piirtyy
    # väärin", 2026-09-16)
    ax_max, y_ticks = _value_axis(max_val, ctx.series.statistic)
    for yv in y_ticks:
        if yv > 0:
            ax.axhline(yv, color=grid, lw=0.8, zorder=1)
    ax.set_yticks(y_ticks)
    ax.set_yticklabels([_tick_text(v) for v in y_ticks], fontsize=9.5, color=muted)
    ax.set_ylim(0, ax_max)

    if ctx.spec.elements.legend and len(segs) > 1:
        style_legend(ax, ctx, loc="best")

    apply_axis_titles(ax, ctx.spec, ink)

    png = render_png(fig)
    place_picture(ctx, png)
