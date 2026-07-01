"""Deterministic SeriesResult constructors for the render integration tests.

Plain builders (not fixtures) so each test composes an exact numeric shape with
no network / no soffice / no compute() dependency. Local to this package.
"""
from __future__ import annotations

from reportbuilder.stats.series import Cell, SeriesResult


def partition_series(cats=("A", "B", "C", "D"), pcts=(40.0, 30.0, 20.0, 10.0)) -> SeriesResult:
    """Single-series additive partition (pct + count sum to base) — pie/doughnut/funnel."""
    cells = {(c, "Total"): Cell(pct=float(p), count=float(p)) for c, p in zip(cats, pcts)}
    return SeriesResult(categories=tuple(cats), segments=("Total",), cells=cells,
                        base_n={"Total": 100}, statistic="pct")


def multiseg_series(cats=("A", "B", "C", "D"), segs=("G1", "G2")) -> SeriesResult:
    """Two-segment series over several categories — bars/line/radar/combo/stacked."""
    cells = {}
    for i, c in enumerate(cats):
        for j, s in enumerate(segs):
            cells[(c, s)] = Cell(pct=float(10 + i * 5 + j * 3), count=float(10 + i))
    return SeriesResult(categories=tuple(cats), segments=tuple(segs), cells=cells,
                        base_n={s: 100 for s in segs}, statistic="pct")


def scatter_series(cats=("A", "B", "C", "D")) -> SeriesResult:
    """Two numeric segments (X, Y) — one (x, y) point per category — scatter."""
    cells = {}
    for i, c in enumerate(cats):
        cells[(c, "X")] = Cell(pct=float(i * 10 + 5))
        cells[(c, "Y")] = Cell(pct=float(100 - i * 7))
    return SeriesResult(categories=tuple(cats), segments=("X", "Y"), cells=cells,
                        base_n={"X": 100, "Y": 100}, statistic="pct")


def word_series(words=None) -> SeriesResult:
    """Word-frequency series: categories = words, each cell.count = frequency."""
    words = words or {"alpha": 10.0, "beta": 6.0, "gamma": 3.0, "delta": 2.0}
    cells = {(w, "Total"): Cell(count=float(f)) for w, f in words.items()}
    return SeriesResult(categories=tuple(words), segments=("Total",), cells=cells,
                        base_n={"Total": 100}, statistic="count")


def empty_series(statistic="pct") -> SeriesResult:
    """No categories — nothing to plot."""
    return SeriesResult(categories=(), segments=("Total",), cells={},
                        base_n={"Total": 0}, statistic=statistic)


def all_zero_series(statistic="pct") -> SeriesResult:
    """Categories present but every value is zero — also 'empty' to plot."""
    cells = {(c, "Total"): Cell(pct=0.0, count=0.0) for c in ("A", "B")}
    return SeriesResult(categories=("A", "B"), segments=("Total",), cells=cells,
                        base_n={"Total": 0}, statistic=statistic)


def series_for(chart_type: str):
    """Return (series, spec_overrides) appropriate for the given image/native type."""
    if chart_type in ("pie", "doughnut"):
        return partition_series(), {}
    if chart_type == "funnel":
        return partition_series(("A", "B", "C"), (80.0, 50.0, 20.0)), {}
    if chart_type == "scatter":
        return scatter_series(), {"scatter_xy": ("X", "Y")}
    if chart_type == "wordcloud":
        return word_series(), {}
    return multiseg_series(), {}
