"""Doughnut chart plugin — same parts-of-a-whole feasibility as the pie, but
never the auto-default (a pie is the default parts-of-whole pick)."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import single_series_schema
from reportbuilder.render.charts.pie import pie_suitability
from reportbuilder.render.image.pie import build_image_doughnut
from reportbuilder.render.native.doughnut import build_doughnut


register(ChartPlugin(
    id="doughnut",
    label="Doughnut Chart",
    image_build=build_image_doughnut,
    native_build=build_doughnut,
    suitability=pie_suitability,  # identical precondition to the pie
    suggest=None,
    config_schema=single_series_schema(),
))
