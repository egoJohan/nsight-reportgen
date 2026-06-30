"""Stacked horizontal bar plugin — multi-group comparisons / Likert-like sets."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import stacked_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.bars import build_image_bar_stacked
from reportbuilder.render.native.bar import build_stacked_horizontal_bar


def suitability(question, series) -> float | None:
    """High for multi-group comparisons (>1 series) or Likert-like (>=4 options)."""
    s = SeriesShape.of(question, series)
    if s.n_series > 1 and s.n_categories >= 2:
        return 0.80
    if s.n_categories >= 4:
        return 0.70
    return 0.40


def suggest(question, series) -> float | None:
    """A rating BATTERY (Likert grid: many statements on one shared scale) defaults
    to a 100%-stacked distribution — the standard research-report format that shows
    how each statement's answers spread across the scale (disagree→agree). Beats
    the plain bar/column suggestion so suitable questions stack by default."""
    if getattr(question, "kind", None) == "battery":
        return 1.20
    return None


register(ChartPlugin(
    id="stacked_horizontal_bar",
    label="Stacked Horizontal Bar",
    image_build=build_image_bar_stacked,
    native_build=build_stacked_horizontal_bar,
    suitability=suitability,
    suggest=suggest,
    config_schema=stacked_schema(),
))
