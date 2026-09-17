"""Radar chart plugin — multi-dimensional profiles (>=4 attributes). Opt-in;
never auto-suggested."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import standard_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.radar import build_image_radar
from reportbuilder.render.native.radar import build_radar


#: Below this a radar has no shape to draw: two spokes make a line through the
#: centre and one makes a point, so the polygon that IS the chart cannot exist.
_MIN_SPOKES = 3


def suitability(question, series) -> float | None:
    """High for multi-dimensional profiles (>=4 attributes); None below three.

    An index — one variable carrying one mean — has a single category, and a
    radar of it drew its rings, one spoke and nothing else: an empty web with a
    label on it. Offering a chart type that cannot draw the question is worse
    than not offering it, because the author has to render it to find out.
    """
    s = SeriesShape.of(question, series)
    if s.n_categories < _MIN_SPOKES:
        return None
    return 0.80 if s.n_categories >= 4 else 0.40


register(ChartPlugin(
    id="radar",
    label="Radar Chart",
    image_build=build_image_radar,
    native_build=build_radar,
    suitability=suitability,
    suggest=None,
    config_schema=standard_schema(),
))
