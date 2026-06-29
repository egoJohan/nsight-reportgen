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


def _looks_ordinal(series) -> bool:
    """True when the categories look like an ordered scale (Likert/age bands)
    rather than nominal groups — i.e. most labels start with a digit
    ("1=Erittäin huonosti", "55-64 vuotta"). A pie reads composition, not order,
    so ordered scales keep bars."""
    import re

    cats = [c for c in series.categories if c]
    if not cats:
        return False
    digit_start = sum(1 for c in cats if re.match(r"^\s*\d", c))
    return digit_start >= len(cats) * 0.5


def pie_suggest(question, series) -> float | None:
    """Default for NOMINAL parts-of-whole (unordered groups, few slices) — a pie
    reads a composition better than a bar there. Ordered scales (Likert, age
    bands) keep bars. A very small partition (<=4) defaults to pie regardless."""
    s = SeriesShape.of(question, series)
    if not _is_parts_of_whole(s):
        return None
    if s.n_categories <= 6 and not _looks_ordinal(series):
        return 0.95  # nominal parts-of-whole → pie is the natural default
    if s.n_categories <= 4:
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
