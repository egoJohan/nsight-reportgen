"""Plugin-local feasibility tests for the pie & doughnut charts.

The principled rule: a pie/doughnut is offered only when the data is a single
series that PARTITIONS a whole (mutually exclusive + exhaustive), shown with an
additive statistic. This lives entirely in the pie/doughnut plugin — adding or
changing it touches no generic code.
"""
from __future__ import annotations

from reportbuilder.render.plugins import plugin
from reportbuilder.stats.series import Cell, SeriesResult


class _Q:
    def __init__(self, kind):
        self.kind = kind


def _single_segment(pairs, base, *, statistic="pct"):
    cats = tuple(p[0] for p in pairs)
    cells = {(p[0], "Total"): Cell(pct=p[1], count=p[2]) for p in pairs}
    return SeriesResult(
        categories=cats, segments=("Total",), cells=cells,
        base_n={"Total": base}, statistic=statistic,
    )


PIE = plugin("pie")
DOUGHNUT = plugin("doughnut")


def test_single_choice_offers_pie():
    """Single-choice distribution partitions the base → pie feasible."""
    s = _single_segment([("Yes", 60.0, 60.0), ("No", 40.0, 40.0)], base=100)
    assert PIE.suitability(_Q("single"), s) is not None
    assert DOUGHNUT.suitability(_Q("single"), s) is not None


def test_multi_response_partition_offers_pie():
    """Multi-response where respondents effectively chose one → partition →
    pie IS offered (the var14 case the user raised)."""
    s = _single_segment(
        [("Public", 59.4, 378.0), ("Private", 32.0, 204.0),
         ("Non-profit", 5.5, 35.0), ("Don't know", 3.1, 19.0)],
        base=636,
    )
    assert PIE.suitability(_Q("multi"), s) is not None
    assert DOUGHNUT.suitability(_Q("multi"), s) is not None


def test_multi_response_overlap_hides_pie():
    """Genuine 'tick several' overlap → shares exceed the base → NOT a partition
    → pie hidden (it would double-count)."""
    s = _single_segment(
        [("A", 70.0, 140.0), ("B", 60.0, 120.0), ("C", 50.0, 100.0)],
        base=200,
    )
    assert PIE.suitability(_Q("multi"), s) is None
    assert DOUGHNUT.suitability(_Q("multi"), s) is None


def test_multiple_series_hides_pie():
    """A classifying variable yields several series; one pie can't show them."""
    s = SeriesResult(
        categories=("A", "B"), segments=("Total", "Men", "Women"),
        cells={
            ("A", "Total"): Cell(pct=60.0, count=60.0),
            ("B", "Total"): Cell(pct=40.0, count=40.0),
            ("A", "Men"): Cell(pct=50.0, count=20.0),
            ("B", "Men"): Cell(pct=50.0, count=20.0),
            ("A", "Women"): Cell(pct=66.0, count=40.0),
            ("B", "Women"): Cell(pct=34.0, count=20.0),
        },
        base_n={"Total": 100, "Men": 40, "Women": 60}, statistic="pct",
    )
    assert PIE.suitability(_Q("single"), s) is None


def test_mean_statistic_hides_pie():
    """A mean is not an additive part of a whole → pie not feasible."""
    s = SeriesResult(
        categories=("A", "B"), segments=("Total",),
        cells={("A", "Total"): Cell(mean=3.4), ("B", "Total"): Cell(mean=2.1)},
        base_n={"Total": 100}, statistic="mean",
    )
    assert PIE.suitability(_Q("single"), s) is None


def test_pie_is_default_for_small_partition_but_not_for_multi():
    """suggest: a small single-choice partition defaults to pie; a multi-response
    partition still defaults to a bar (pie is available, not the default)."""
    small = _single_segment([("Yes", 60.0, 60.0), ("No", 40.0, 40.0)], base=100)
    assert PIE.suggest(_Q("single"), small) is not None
    # Multi-response: horizontal_bar should out-score pie for the default.
    from reportbuilder.render.plugins import suggest_chart_type
    assert suggest_chart_type(_Q("multi"), small) == "horizontal_bar"
