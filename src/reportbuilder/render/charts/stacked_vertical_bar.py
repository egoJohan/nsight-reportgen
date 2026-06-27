"""Stacked vertical bar plugin — Likert/ordered distributions (>=4 options)."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import stacked_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.bars import build_image_column_stacked
from reportbuilder.render.native.bar import build_stacked_vertical_bar


def suitability(question, series) -> float | None:
    """High for Likert-like distributions (>=4 response options)."""
    s = SeriesShape.of(question, series)
    return 0.75 if s.n_categories >= 4 else 0.40


register(ChartPlugin(
    id="stacked_vertical_bar",
    label="Stacked Vertical Bar",
    image_build=build_image_column_stacked,
    native_build=build_stacked_vertical_bar,
    suitability=suitability,
    suggest=None,  # available but never the auto-default
    config_schema=stacked_schema(),
))
