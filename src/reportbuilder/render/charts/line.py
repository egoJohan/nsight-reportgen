"""Line chart plugin — the default for time/wave (temporal) categories."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import standard_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.line import build_image_line
from reportbuilder.render.native.line import build_line


def suitability(question, series) -> float | None:
    """High when categories look temporal; moderate for >=3 ordered categories."""
    s = SeriesShape.of(question, series)
    if s.is_temporal:
        return 0.90
    return 0.60 if s.n_categories >= 3 else 0.35


def suggest(question, series) -> float | None:
    """Auto-default only for temporal categories (a trend over time/waves)."""
    s = SeriesShape.of(question, series)
    return 1.00 if s.is_temporal else None


register(ChartPlugin(
    id="line",
    label="Line Chart",
    image_build=build_image_line,
    native_build=build_line,
    suitability=suitability,
    suggest=suggest,
    config_schema=standard_schema(),
))
