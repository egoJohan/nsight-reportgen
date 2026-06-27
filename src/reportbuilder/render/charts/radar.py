"""Radar chart plugin — multi-dimensional profiles (>=4 attributes). Opt-in;
never auto-suggested."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import standard_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.radar import build_image_radar
from reportbuilder.render.native.radar import build_radar


def suitability(question, series) -> float | None:
    """High for multi-dimensional profiles (>=4 attributes)."""
    s = SeriesShape.of(question, series)
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
