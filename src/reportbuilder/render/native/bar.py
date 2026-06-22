"""Native bar chart builders: horizontal, stacked vertical, stacked horizontal (Task 5.5).

REQ-C-13, C-24b/g.

All builders follow the same contract as build_vertical_bar in column.py:
- Accept a RenderContext (ctx).
- Create the chart from ctx.series + ctx.slot geometry.
- Apply per-series colors from ctx.style.
- Return the graphic frame.
- Do NOT call apply_elements (deck assembly in Task 5.14 does that).
"""
from __future__ import annotations
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from reportbuilder.render.base import RenderContext
from reportbuilder.render.native.column import series_chart_data


def _build_bar(ctx: RenderContext, chart_type: XL_CHART_TYPE, *, stacked: bool = False):
    """Shared inner helper: create a bar/column chart and apply colors.

    Args:
        ctx: render context with slide, slot, series, and style.
        chart_type: one of the XL_CHART_TYPE bar/column constants.
        stacked: if True, set plot overlap to 100 (stacked variants).

    Returns:
        The graphic frame containing the chart.
    """
    cd = series_chart_data(ctx.series, ctx.series.statistic)
    gf = ctx.slide.shapes.add_chart(
        chart_type,
        ctx.slot.left,
        ctx.slot.top,
        ctx.slot.width,
        ctx.slot.height,
        cd,
    )
    plot = gf.chart.plots[0]
    if stacked:
        plot.overlap = 100
    for i, ser in enumerate(plot.series):
        ser.format.fill.solid()
        ser.format.fill.fore_color.rgb = RGBColor.from_string(ctx.style.color_for(i))
    return gf


def build_horizontal_bar(ctx: RenderContext):
    """Native horizontal (clustered) bar chart.

    Uses XL_CHART_TYPE.BAR_CLUSTERED → c:barChart with barDir='bar'.
    """
    return _build_bar(ctx, XL_CHART_TYPE.BAR_CLUSTERED)


def build_stacked_vertical_bar(ctx: RenderContext):
    """Native stacked vertical bar (column) chart.

    Uses XL_CHART_TYPE.COLUMN_STACKED → c:barChart with barDir='col' +
    grouping='stacked'. Overlap is set to 100.
    """
    return _build_bar(ctx, XL_CHART_TYPE.COLUMN_STACKED, stacked=True)


def build_stacked_horizontal_bar(ctx: RenderContext):
    """Native stacked horizontal bar chart.

    Uses XL_CHART_TYPE.BAR_STACKED → c:barChart with barDir='bar' +
    grouping='stacked'. Overlap is set to 100.
    """
    return _build_bar(ctx, XL_CHART_TYPE.BAR_STACKED, stacked=True)
