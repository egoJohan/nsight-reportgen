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

OFFERING-side tolerance (this module only — NOT a change to `is_partition()`'s
own default): real single-choice survey data routinely excludes a small "no
answer"/other slice from the named categories while still counting it in the
base, so the shares land a bit short of 100% (an audit of the store's saved
partition-assuming charts found this on ~50 legitimate single-choice slides,
shortfalls of 0.2-2%, invisible once the pie renormalises to fill the circle).
That shortfall must NOT cost those questions their pie. Overshoot gets no such
slack: it's exactly what a genuinely overlapping multi-response set produces
(two real slides in that same audit summed to 462% and 800%), so it stays
bound by `is_partition()`'s own strict, float-noise-only `tol`. Hence we call
`series.is_partition(..., undershoot_tol=_UNDERSHOOT_TOL_PCT)` here rather than
reading the (deliberately strict) `SeriesShape.is_partition` field.
"""
from __future__ import annotations

from reportbuilder.render.plugins import ChartPlugin, register
from reportbuilder.render.config_schema import single_series_schema
from reportbuilder.render.panels import panel_segments
from reportbuilder.render.shape import ADDITIVE_STATISTICS, SeriesShape
from reportbuilder.render.image.pie import build_image_pie
from reportbuilder.render.native.pie import build_pie
from reportbuilder.stats.series import PARTITION_UNDERSHOOT_TOL_PCT

# Percent-of-base shortfall a pie/doughnut still tolerates (see module
# docstring): comfortably above the ~2% worst case observed in legitimate
# single-choice data, nowhere near the 100+ percentage points genuine
# multi-response overlap produces. Defined once next to `is_partition` itself
# (stats/series.py) — the stacked-bar renderer reads the SAME constant, so the
# two never drift apart.
_UNDERSHOOT_TOL_PCT = PARTITION_UNDERSHOOT_TOL_PCT


def _is_parts_of_whole(question, series) -> bool:
    """The structural precondition shared by pie and doughnut.

    With a classifier the chart is one pie PER GROUP, so the question is asked of
    every panel that will actually be drawn: a question can partition the whole
    sample and still fail inside a thin group, and that group's pie is the one that
    would not add up. Groups that will NOT be drawn — dropped for a thin base or
    beyond the three-panel cap — cannot veto the chart type, because nothing will
    render them. (spec 2026-08-22)
    """
    s = SeriesShape.of(question, series)
    if s.statistic not in ADDITIVE_STATISTICS:
        return False
    panels = panel_segments(series).labels
    if not panels:
        return False
    return all(series.is_partition(seg, undershoot_tol=_UNDERSHOOT_TOL_PCT)
               for seg in panels)


def pie_suitability(question, series) -> float | None:
    """None (hidden) unless the data is a single-series partition of a whole."""
    if not _is_parts_of_whole(question, series):
        return None
    s = SeriesShape.of(question, series)
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
    bands) keep bars. A very small partition (<=4) defaults to pie regardless.

    A SPLIT series is never auto-suggested: a row of pies is an explicit choice by
    the author, not a default the tool makes for them. Offering it (`pie_suitability`)
    and defaulting to it are different questions. (ruling, 2026-08-22)
    """
    if panel_segments(series).split:
        return None
    if not _is_parts_of_whole(question, series):
        return None
    s = SeriesShape.of(question, series)
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
