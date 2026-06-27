"""SeriesResult.is_partition — the principled parts-of-a-whole precondition.

A pie/doughnut is faithful only when the categories partition the base: every
counted unit falls in exactly one category (mutually exclusive + exhaustive).
Because the multi-response base is "respondents with >=1 selection" (not total
selections), this is exactly: the category counts sum to the base.
"""
from __future__ import annotations

from reportbuilder.stats.series import Cell, SeriesResult


def _series(pairs, base, *, statistic="pct", segment="Total"):
    """pairs: list[(label, pct, count)] for a single segment."""
    cats = tuple(p[0] for p in pairs)
    cells = {(p[0], segment): Cell(pct=p[1], count=p[2]) for p in pairs}
    return SeriesResult(
        categories=cats, segments=(segment,), cells=cells,
        base_n={segment: base}, statistic=statistic,
    )


def test_single_choice_distribution_is_partition():
    """Counts sum to the base (each respondent in exactly one category)."""
    s = _series([("Yes", 60.0, 3.0), ("No", 40.0, 2.0)], base=5)
    assert s.is_partition() is True


def test_multi_response_no_overlap_is_partition():
    """A 'pick all that apply' set where respondents effectively chose one:
    counts still sum to the base, so the shares are genuine parts of a whole."""
    s = _series(
        [("Public", 59.4, 378.0), ("Private", 32.0, 204.0),
         ("Non-profit", 5.5, 35.0), ("Don't know", 3.1, 19.0)],
        base=636,
    )
    assert s.is_partition() is True


def test_multi_response_with_overlap_is_not_partition():
    """Genuine multi-select: selections exceed respondents -> counts overrun the
    base -> not a partition -> a pie would double-count."""
    s = _series(
        [("A", 70.0, 140.0), ("B", 60.0, 120.0), ("C", 50.0, 100.0)],
        base=200,
    )
    assert s.is_partition() is False


def test_partition_falls_back_to_pct_when_counts_missing():
    """No counts present -> use the percentage shares (sum ~= 100%)."""
    s = SeriesResult(
        categories=("A", "B"), segments=("Total",),
        cells={("A", "Total"): Cell(pct=55.0), ("B", "Total"): Cell(pct=45.0)},
        base_n={"Total": 100}, statistic="pct",
    )
    assert s.is_partition() is True


def test_multiple_segments_is_not_partition():
    """More than one series can't be a single pie's whole."""
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
    # Default segment "Total" partitions, but n_series > 1 is handled by the
    # pie plugin (single-series rule), not here. is_partition reports the
    # Total segment's partition status.
    assert s.is_partition() is True
    assert s.n_series == 3
