"""Funnel chart plugin — ordered-descending single series (awareness funnel).
Opt-in: never auto-suggested even when the shape fits."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import single_series_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.funnel import build_image_funnel
from reportbuilder.render.native.funnel import build_funnel


def suitability(question, series) -> float | None:
    """High for an ordered-descending single series; low otherwise.

    Reads the actual values (descending-ness is a value property, not captured by
    the structural SeriesShape) for the single series.
    """
    s = SeriesShape.of(question, series)
    if s.n_series != 1 or s.n_categories < 3:
        return 0.30
    seg = series.segments[0]
    vals = [series.cell(c, seg).value(series.statistic) or 0.0 for c in series.categories]
    is_desc = all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1))
    return 0.85 if is_desc else 0.50


register(ChartPlugin(
    id="funnel",
    label="Funnel Chart",
    image_build=build_image_funnel,
    native_build=build_funnel,
    suitability=suitability,
    suggest=None,
    config_schema=single_series_schema(),  # single series → no classifying variable
))
