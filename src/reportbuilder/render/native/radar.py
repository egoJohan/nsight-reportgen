"""Native radar chart builder (Task 5.7).

REQ-C-13, C-24g.

Builder contract (same as column.py / bar.py / line.py):
- Accept RenderContext.
- Create the chart from ctx.series + ctx.slot geometry.
- Apply per-series colors from ctx.style via the series line color (like line charts).
- Return the graphic frame.
- Do NOT call apply_elements (deck assembly in Task 5.14 does that).
"""
from __future__ import annotations
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from reportbuilder.render.base import RenderContext
from reportbuilder.render.native.column import series_chart_data


def build_radar(ctx: RenderContext):
    """Native radar chart with markers (RADAR_MARKERS).

    Colors each series via the line stroke color (ser.format.line.color.rgb),
    matching the approach used by line charts.

    Args:
        ctx: render context with slide, slot, series, and style.

    Returns:
        The graphic frame containing the chart.
    """
    cd = series_chart_data(ctx.series, ctx.series.statistic)
    gf = ctx.slide.shapes.add_chart(
        XL_CHART_TYPE.RADAR_MARKERS,
        ctx.slot.left,
        ctx.slot.top,
        ctx.slot.width,
        ctx.slot.height,
        cd,
    )
    for i, ser in enumerate(gf.chart.plots[0].series):
        ser.format.line.color.rgb = RGBColor.from_string(ctx.style.color_for(i))
    return gf
