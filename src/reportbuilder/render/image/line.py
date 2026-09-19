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
    colours_by_series, _value_axis, author_label_floor,
)
from reportbuilder.render.house_style import series_colors
from reportbuilder.render.image._mpl import template_palette
from reportbuilder.render.image._mpl import VALUE_GID
from reportbuilder.render.image.label_fit import names_flat_unless_they_cannot_be



def _tick_text(v: float) -> str:
    """A tick label without a pointless ".0" — counts are whole numbers, and a
    mean's ticks may not be."""
    return str(int(v)) if float(v).is_integer() else f"{v:g}"

#: Clear space kept between two numbers stacked in one category's column.
_STACK_GAP_PT: float = 1.5


def spread_values_in_columns(fig, ax) -> int:
    """Move apart the numbers that several lines print at one category.

    Every point's number sits a fixed 7pt above it, so wherever two lines pass
    close together their numbers land on each other — "50 %" through "49 %"
    through "46 %" — on every line chart split by a classifier (visual QA,
    2026-09-19: up to 105 collisions on one slide). Nothing is hidden to make
    room (Johan, 2026-09-13): in each category's column the numbers keep the
    vertical order of their points and are pushed apart around where they
    wanted to be — the order is what ties each number to its line. (Leaders were
    tried: in a column of three, the outer number's leader ran straight through
    the middle one, "3|0".)

    The same number for the same point, printed once per line — three groups
    all at "0 %" on one marker — is printed once: it is one number, at one
    place, and the stack of copies only buried the others.

    Returns how many numbers moved.
    """
    from collections import defaultdict

    labels = [t for t in ax.texts
              if t.get_gid() == VALUE_GID and t.get_visible() and hasattr(t, "xyann")]
    if len(labels) < 2:
        return 0
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    pt = fig.dpi / 72.0
    gap = _STACK_GAP_PT * pt
    columns: dict = defaultdict(list)
    for t in labels:
        columns[round(float(t.xy[0]), 6)].append(t)
    moved = 0
    for col in columns.values():
        seen: dict = {}
        for t in col:
            key = (t.get_text(), round(float(t.xy[1]), 9))
            if key in seen:
                t.set_visible(False)
            else:
                seen[key] = t
        col = list(seen.values())
        if len(col) < 2:
            continue
        items = []
        for t in col:
            bb = t.get_window_extent(r)
            items.append((t, (bb.y0 + bb.y1) / 2, bb.height))
        items.sort(key=lambda it: it[1])

        def layout(cluster):
            total = sum(h for _t, _y, h in cluster) + gap * (len(cluster) - 1)
            y = sum(want for _t, want, _h in cluster) / len(cluster) - total / 2
            out = []
            for _t, _want, h in cluster:
                out.append(y + h / 2)
                y += h + gap
            return out

        clusters = [[it] for it in items]
        merged = True
        while merged:
            merged = False
            for i in range(len(clusters) - 1):
                a, b = layout(clusters[i]), layout(clusters[i + 1])
                if a[-1] + clusters[i][-1][2] / 2 + gap > b[0] - clusters[i + 1][0][2] / 2:
                    clusters[i:i + 2] = [clusters[i] + clusters[i + 1]]
                    merged = True
                    break
        for cluster in clusters:
            for (t, want, h), got in zip(cluster, layout(cluster)):
                shift = got - want
                if abs(shift) < 0.5:
                    continue
                moved += 1
                dx, dy = t.xyann
                t.xyann = (dx, dy + shift / pt)
    return moved


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
    default_segs, segs = segs, place_total(segs, getattr(ctx.spec, "total_position", "auto"))
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
                    # On a pad of the ground, as the combo's line numbers are:
                    # a steep segment ran straight through "15 %" beside its
                    # own marker. (visual QA, 2026-09-19)
                    bbox={"boxstyle": "round,pad=0.15", "facecolor": bg,
                          "edgecolor": "none", "alpha": 0.85},
                )

    ax.set_xticks(x)
    # Half a category of room at either end, as every column chart has. With
    # matplotlib's default 5 % the first and last points sat at the plot's
    # edges, so their names reached out past it — the first straight into the
    # value axis's "0" — and a long one could only be printed rotated.
    # (visual QA, 2026-09-19)
    ax.set_xlim(-0.5, len(cats) - 0.5)
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

    # Category labels — flat when they fit in full, rotated only when they
    # cannot. This rotated whenever there were more than four names or one
    # longer than 16 characters, however much room the axis had. Set once the
    # value axis is, so its numbers are there to be kept clear of.
    # See `names_flat_unless_they_cannot_be`. (visual QA, 2026-09-19)
    # Through the shared rule: a lone SUMMARY category is the question itself,
    # and printing it under the axis repeats the subtitle as an axis title
    # nobody asked for. See `_category_ticks`. (Johan, 2026-09-16)
    names_flat_unless_they_cannot_be(
        fig, ax, _category_ticks(cats, str, ctx.series.statistic),
        fontsize=11.5, rotated_fontsize=10.5, color=ink, width=16,
        wrap=wrap_label, rotation=25)

    # Several lines put their numbers in one column per category; spread them
    # before the legend picks its corner, so it sees where they finally are.
    spread_values_in_columns(fig, ax)

    if ctx.spec.elements.legend and len(segs) > 1:
        style_legend(ax, ctx, loc="best")

    apply_axis_titles(ax, ctx.spec, ink)

    png = render_png(fig)
    place_picture(ctx, png)
