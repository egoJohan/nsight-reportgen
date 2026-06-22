"""Image-mode bar/column chart builders (Task 5.11).

Builders: build_image_column, build_image_bar,
          build_image_column_stacked, build_image_bar_stacked.

Each renders to PNG via matplotlib (Agg) and places the image with add_picture.
Returns None.
"""
from __future__ import annotations
import numpy as np
from reportbuilder.render.image._mpl import (
    new_figure, render_png, place_picture, series_values, colors,
)


def build_image_column(ctx) -> None:
    """Vertical grouped bar chart (one bar group per category, one bar per segment)."""
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    clrs = colors(ctx, len(segs))

    x = np.arange(len(cats))
    n_segs = len(segs)
    width = 0.8 / n_segs if n_segs > 1 else 0.5

    for i, seg in enumerate(segs):
        vals = data[seg]
        offset = (i - n_segs / 2 + 0.5) * width if n_segs > 1 else 0.0
        bars = ax.bar(x + offset, vals, width=width, label=seg, color=clrs[i])
        if ctx.spec.elements.data_labels:
            for bar, v in zip(bars, vals):
                ax.annotate(
                    f"{v:.0f}",
                    xy=(bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    xytext=(0, 2),
                    textcoords="offset points",
                    ha="center", va="bottom", fontsize=7,
                )

    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=8)
    if ctx.spec.elements.title:
        ax.set_title("")
    if ctx.spec.elements.legend and n_segs > 1:
        ax.legend(fontsize=7)

    png = render_png(fig)
    place_picture(ctx, png)


def build_image_bar(ctx) -> None:
    """Horizontal grouped bar chart (barh)."""
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    clrs = colors(ctx, len(segs))

    y = np.arange(len(cats))
    n_segs = len(segs)
    height = 0.8 / n_segs if n_segs > 1 else 0.5

    for i, seg in enumerate(segs):
        vals = data[seg]
        offset = (i - n_segs / 2 + 0.5) * height if n_segs > 1 else 0.0
        bars = ax.barh(y + offset, vals, height=height, label=seg, color=clrs[i])
        if ctx.spec.elements.data_labels:
            for bar, v in zip(bars, vals):
                ax.annotate(
                    f"{v:.0f}",
                    xy=(bar.get_width(), bar.get_y() + bar.get_height() / 2),
                    xytext=(2, 0),
                    textcoords="offset points",
                    ha="left", va="center", fontsize=7,
                )

    ax.set_yticks(y)
    ax.set_yticklabels(cats, fontsize=8)
    if ctx.spec.elements.title:
        ax.set_title("")
    if ctx.spec.elements.legend and n_segs > 1:
        ax.legend(fontsize=7)

    png = render_png(fig)
    place_picture(ctx, png)


def build_image_column_stacked(ctx) -> None:
    """Stacked vertical bar chart."""
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    clrs = colors(ctx, len(segs))

    x = np.arange(len(cats))
    bottoms = np.zeros(len(cats))

    for i, seg in enumerate(segs):
        vals = np.array(data[seg])
        bars = ax.bar(x, vals, bottom=bottoms, label=seg, color=clrs[i])
        if ctx.spec.elements.data_labels:
            for bar, v, b in zip(bars, vals, bottoms):
                mid = b + v / 2
                if v > 0:
                    ax.annotate(
                        f"{v:.0f}",
                        xy=(bar.get_x() + bar.get_width() / 2, mid),
                        ha="center", va="center", fontsize=7,
                    )
        bottoms += vals

    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontsize=8)
    if ctx.spec.elements.title:
        ax.set_title("")
    if ctx.spec.elements.legend and len(segs) > 1:
        ax.legend(fontsize=7)

    png = render_png(fig)
    place_picture(ctx, png)


def build_image_bar_stacked(ctx) -> None:
    """Stacked horizontal bar chart."""
    cats, segs, data = series_values(ctx.series)
    fig, ax = new_figure(ctx)
    clrs = colors(ctx, len(segs))

    y = np.arange(len(cats))
    lefts = np.zeros(len(cats))

    for i, seg in enumerate(segs):
        vals = np.array(data[seg])
        bars = ax.barh(y, vals, left=lefts, label=seg, color=clrs[i])
        if ctx.spec.elements.data_labels:
            for bar, v, l in zip(bars, vals, lefts):
                mid = l + v / 2
                if v > 0:
                    ax.annotate(
                        f"{v:.0f}",
                        xy=(mid, bar.get_y() + bar.get_height() / 2),
                        ha="center", va="center", fontsize=7,
                    )
        lefts += vals

    ax.set_yticks(y)
    ax.set_yticklabels(cats, fontsize=8)
    if ctx.spec.elements.title:
        ax.set_title("")
    if ctx.spec.elements.legend and len(segs) > 1:
        ax.legend(fontsize=7)

    png = render_png(fig)
    place_picture(ctx, png)
