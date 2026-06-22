"""Native pie chart builder (Task 5.6).

REQ-C-13, C-24b/f.

Builder contract (same as column.py / bar.py):
- Accept RenderContext.
- Create the chart from ctx.series + ctx.slot geometry.
- Apply per-point colors from ctx.style (pie uses one series; color each point).
- Return the graphic frame.
- Do NOT call apply_elements (deck assembly in Task 5.14 does that).
"""
from __future__ import annotations
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from reportbuilder.render.base import RenderContext
from reportbuilder.render.native.column import series_chart_data


def build_pie(ctx: RenderContext):
    """Native pie chart.

    Pie has one series (the first/only segment). Each category slice is
    colored individually via per-point fill formatting.

    Args:
        ctx: render context with slide, slot, series, and style.

    Returns:
        The graphic frame containing the chart.
    """
    cd = series_chart_data(ctx.series, ctx.series.statistic)
    gf = ctx.slide.shapes.add_chart(
        XL_CHART_TYPE.PIE,
        ctx.slot.left,
        ctx.slot.top,
        ctx.slot.width,
        ctx.slot.height,
        cd,
    )
    pts = gf.chart.plots[0].series[0].points
    for i, pt in enumerate(pts):
        pt.format.fill.solid()
        pt.format.fill.fore_color.rgb = RGBColor.from_string(ctx.style.color_for(i))
    return gf
