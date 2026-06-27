"""Combo (dual-axis) chart plugin — moderate for multi-series comparison."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import standard_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.combo import build_image_combo
from reportbuilder.render.native.combo import build_combo_native


def suitability(question, series) -> float | None:
    """Moderate for dual-axis comparison (>=2 series)."""
    s = SeriesShape.of(question, series)
    return 0.60 if s.n_series >= 2 else 0.30


register(ChartPlugin(
    id="combo",
    label="Combo Chart",
    image_build=build_image_combo,
    native_build=build_combo_native,
    suitability=suitability,
    suggest=None,
    config_schema=standard_schema(),
))
