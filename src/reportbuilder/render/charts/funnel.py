"""Funnel chart plugin — ordered-descending single series (awareness funnel).
Opt-in: never auto-suggested even when the shape fits."""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import single_series_schema
from reportbuilder.render.shape import SeriesShape
from reportbuilder.render.image.funnel import build_image_funnel
from reportbuilder.render.native.funnel import build_funnel
from reportbuilder.render.panels import panel_segments


def suitability(question, series) -> float | None:
    """High for an ordered-descending series, judged on every panel drawn.

    Descending-ness is a value property, not captured by the structural
    SeriesShape, so it is read from the data. With a classifier the funnel is one
    funnel PER GROUP (spec 2026-08-22), so every drawn panel must descend — a
    group that climbs would get a funnel pointing the wrong way.
    """
    s = SeriesShape.of(question, series)
    if s.n_categories < 3:
        return 0.30
    panels = panel_segments(series).labels
    if not panels:
        return 0.30
    for seg in panels:
        vals = [series.cell(c, seg).value(series.statistic) or 0.0
                for c in series.categories]
        if not all(vals[i] >= vals[i + 1] for i in range(len(vals) - 1)):
            return 0.50
    return 0.85


register(ChartPlugin(
    id="funnel",
    label="Funnel Chart",
    image_build=build_image_funnel,
    native_build=build_funnel,
    suitability=suitability,
    suggest=None,
    config_schema=single_series_schema(),  # single series → no classifying variable
))
