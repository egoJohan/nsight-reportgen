"""Pie chart plugin — parts of ONE whole.

Feasibility is principled, not a magic threshold: a pie faithfully represents
the data only when the categories **partition the base** (every respondent
counted in exactly one category — mutually exclusive AND exhaustive) within a
single series.  ``SeriesResult.is_partition()`` decides this exactly from the
data, so:

- single-choice questions     → always a partition → pie feasible;
- multi-response where people effectively chose one (shares sum to the base)
                              → a genuine partition → pie feasible;
- multi-response with real overlap (shares exceed the base)
                              → not a partition → pie would double-count → hidden.

A pie also needs an additive statistic (percentage/count, never a mean) and a
single series (a classifying variable splits the data into several series, which
a single pie cannot show).
"""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import single_series_schema
from reportbuilder.render.shape import ADDITIVE_STATISTICS, SeriesShape
from reportbuilder.render.image.pie import build_image_pie
from reportbuilder.render.native.pie import build_pie


def _is_parts_of_whole(s: SeriesShape) -> bool:
    """The structural precondition shared by pie and doughnut."""
    return (
        s.n_series == 1
        and s.statistic in ADDITIVE_STATISTICS
        and s.is_partition
    )


def pie_suitability(question, series) -> float | None:
    """None (hidden) unless the data is a single-series partition of a whole."""
    s = SeriesShape.of(question, series)
    if not _is_parts_of_whole(s):
        return None
    return 0.75 if s.n_categories <= 6 else 0.50


def pie_suggest(question, series) -> float | None:
    """Auto-default only for a small parts-of-whole set (<=4 slices)."""
    s = SeriesShape.of(question, series)
    if _is_parts_of_whole(s) and s.n_categories <= 4:
        return 0.60
    return None


register(ChartPlugin(
    id="pie",
    label="Pie Chart",
    image_build=build_image_pie,
    native_build=build_pie,
    suitability=pie_suitability,
    suggest=pie_suggest,
    config_schema=single_series_schema(),  # single series → no classifying variable
))
