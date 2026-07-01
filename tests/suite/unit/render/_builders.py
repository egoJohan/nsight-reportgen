"""Local, import-safe series/question builders for the render-layer unit tests.

Not a conftest and not a fixture module — just plain constructors so each test
can compose an exact SeriesResult/Question shape deterministically (no network,
no soffice, no matplotlib rendering).
"""
from __future__ import annotations

from reportbuilder.model.question import Question
from reportbuilder.stats.series import Cell, SeriesResult


def q(kind: str = "single", qid: str = "q", n_vars: int = 1) -> Question:
    return Question(qid=qid, kind=kind,
                    variables=tuple(f"v{i}" for i in range(n_vars)), text="Q")


def _pick(m, c, default):
    if m is None:
        return default
    if isinstance(m, dict):
        return m.get(c, default)
    return m


def build_series(cats, *, segs=("Total",), statistic="pct", base=100,
                 pct=None, count=None, mean=None) -> SeriesResult:
    """Flexible SeriesResult builder.

    pct/count/mean may each be a scalar (same for every cell), a dict keyed by
    category label, or None (leaves that stat empty on the cell).
    """
    cells = {}
    for c in cats:
        for s in segs:
            cells[(c, s)] = Cell(pct=_pick(pct, c, None),
                                 count=_pick(count, c, None),
                                 mean=_pick(mean, c, None))
    return SeriesResult(categories=tuple(cats), segments=tuple(segs),
                        cells=cells, base_n={s: base for s in segs},
                        statistic=statistic)


# ---- Named shapes used across the render-layer tests ----------------------

def few_short_series() -> SeriesResult:
    """1 series, 2 short-label categories, a genuine partition (pct sums 100)."""
    return build_series(("Yes", "No"), statistic="pct", base=100,
                        pct={"Yes": 60.0, "No": 40.0},
                        count={"Yes": 60.0, "No": 40.0})


def many_long_series() -> SeriesResult:
    """1 series, 8 long-label categories (>6 cats, labels >14 chars)."""
    cats = tuple(f"Category number {i}" for i in range(8))
    return build_series(cats, statistic="pct", base=100, pct=12.0, count=12.0)


def partition_series() -> SeriesResult:
    """Single-series additive partition (counts sum to base)."""
    return build_series(("A", "B", "C", "D"), statistic="pct", base=100,
                        pct={"A": 40.0, "B": 30.0, "C": 20.0, "D": 10.0},
                        count={"A": 40.0, "B": 30.0, "C": 20.0, "D": 10.0})


def nonpartition_series() -> SeriesResult:
    """Counts do NOT sum to the base -> not a partition."""
    return build_series(("A", "B", "C"), statistic="pct", base=100,
                        pct=50.0, count=10.0)


def mean_series() -> SeriesResult:
    """A mean statistic (non-additive) -> never parts-of-a-whole."""
    return build_series(("A", "B", "C", "D"), statistic="mean", base=100,
                        mean={"A": 3.1, "B": 3.4, "C": 2.9, "D": 4.0})


def temporal_series() -> SeriesResult:
    """Categories look like a time/wave axis (years)."""
    return build_series(("2019", "2020", "2021", "2022"), statistic="pct",
                        base=100, pct=50.0)


def descending_series() -> SeriesResult:
    """1 series, >=3 categories, values strictly descending (funnel-shaped)."""
    return build_series(("A", "B", "C", "D"), statistic="pct", base=100,
                        pct={"A": 80.0, "B": 55.0, "C": 30.0, "D": 10.0})


def ascending_series() -> SeriesResult:
    return build_series(("A", "B", "C", "D"), statistic="pct", base=100,
                        pct={"A": 10.0, "B": 30.0, "C": 55.0, "D": 80.0})


def multi_group_series() -> SeriesResult:
    """2 segments (a classifying split) across 4 categories."""
    return build_series(("A", "B", "C", "D"), segs=("G1", "G2"),
                        statistic="pct", base=100, pct=25.0, count=25.0)


def empty_series() -> SeriesResult:
    return SeriesResult(categories=(), segments=("Total",), cells={},
                        base_n={"Total": 0}, statistic="pct")
