"""Scatter plot plugin — requires explicit X/Y configuration (scatter_xy); never
auto-suggested and not offered through generic suitability."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import note_field
from reportbuilder.render.image.scatter import build_image_scatter
from reportbuilder.render.native.scatter import build_scatter


def suitability(question, series) -> float | None:
    """Always None — scatter needs deliberate scatter_xy configuration."""
    return None


register(ChartPlugin(
    id="scatter",
    label="Scatter Plot",
    image_build=build_image_scatter,
    native_build=build_scatter,
    suitability=suitability,
    suggest=None,
    requires=("scatter_xy",),
    config_schema=(note_field("Scatter configuration coming soon."),),
))
