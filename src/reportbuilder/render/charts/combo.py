"""Combo (dual-axis) chart plugin — moderate for multi-series comparison."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import combo_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.combo import build_image_combo
from reportbuilder.render.native.combo import build_combo_native


def suitability(question, series) -> float | None:
    """A single-question x-axis works with a secondary variable; a multi-series
    split also works. Offered broadly (a secondary variable can always be added)."""
    s = SeriesShape.of(question, series)
    return 0.60 if s.n_series >= 2 else 0.45


register(ChartPlugin(
    id="combo",
    label="Combo Chart",
    image_build=build_image_combo,
    native_build=build_combo_native,
    suitability=suitability,
    suggest=None,
    config_schema=combo_schema(),
))
