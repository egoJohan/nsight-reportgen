"""Scatter plot plugin — positions each CATEGORY by its value in two segments.

Not auto-suggested: a scatter answers a question nobody asks by accident ("how
did these attributes move between the two waves?"), and suggesting it for every
split question would bury the chart types people do want. It IS offered once
the data can carry one — a classifying variable with at least two groups —
because the alternative is a chart type the product lists and nobody can reach.
"""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import (
    classifying_var_field, scatter_xy_field,
)
from reportbuilder.render.image.scatter import build_image_scatter
from reportbuilder.render.native.scatter import build_scatter


def suitability(question, series) -> float | None:
    """Offered, never suggested.

    Needs two groups to plot against each other; below that there is nothing to
    position a point with. Scored low on purpose — it should sit at the bottom
    of the picker, available to somebody who wants it and never the default.
    """
    segs = [s for s in getattr(series, "segments", ()) if s != "Total"]
    return 0.05 if len(segs) >= 2 else None
    return None


register(ChartPlugin(
    id="scatter",
    label="Scatter Plot",
    image_build=build_image_scatter,
    native_build=build_scatter,
    suitability=suitability,
    suggest=None,
    requires=("scatter_xy",),
    config_schema=(classifying_var_field(), scatter_xy_field()),
))
