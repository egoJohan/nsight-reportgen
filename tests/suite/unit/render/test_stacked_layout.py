"""Unit tests for `_stacked_layout` — the decomposition behind 100%-stacked bars.

Covers the total-only case (no classifying variable): the single 'Total' column
IS the one bar, stacked by the question's answer categories.
"""
from __future__ import annotations

from reportbuilder.render.image.bars import _stacked_layout
from reportbuilder.stats.series import Cell, SeriesResult


def _total_only_series() -> SeriesResult:
    cells = {
        ("Yes", "Total"): Cell(65.0, None, None),
        ("No", "Total"): Cell(35.0, None, None),
    }
    return SeriesResult(categories=("Yes", "No"), segments=("Total",),
                        cells=cells, base_n={"Total": 100}, statistic="pct")


def test_total_only_is_single_total_bar():
    """No classifier → ONE 'Total' bar whose stack is the answer categories."""
    bars, stack, data = _stacked_layout(_total_only_series())
    assert list(bars) == ["Total"]
    assert list(stack) == ["Yes", "No"]
    assert data["Yes"] == [65.0]
    assert data["No"] == [35.0]


def test_total_only_single_bar_sums_to_100():
    _, stack, data = _stacked_layout(_total_only_series())
    assert abs(sum(data[c][0] for c in stack) - 100.0) < 1e-6


def test_with_classifier_still_transposes_to_segment_bars():
    """Regression: real classifier segments remain the bars, categories the stack."""
    cells = {
        ("Yes", "A"): Cell(60.0, None, None), ("No", "A"): Cell(40.0, None, None),
        ("Yes", "B"): Cell(70.0, None, None), ("No", "B"): Cell(30.0, None, None),
        ("Yes", "Total"): Cell(65.0, None, None), ("No", "Total"): Cell(35.0, None, None),
    }
    s = SeriesResult(categories=("Yes", "No"), segments=("A", "B", "Total"),
                     cells=cells, base_n={"Total": 100, "A": 50, "B": 50}, statistic="pct")
    bars, stack, data = _stacked_layout(s)
    # Real classifier segments are the bars; the overall 'Total' is kept as a trailing
    # reference bar (show_total defaults on). Off → excluded.
    assert bars == ["A", "B", "Total"]
    assert list(stack) == ["Yes", "No"]
    import dataclasses
    bars_off, _, _ = _stacked_layout(dataclasses.replace(s, show_total=False))
    assert bars_off == ["A", "B"]
