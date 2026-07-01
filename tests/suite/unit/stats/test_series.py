"""Unit tests for reportbuilder.stats.series (Cell / SeriesResult)."""
from __future__ import annotations

import pytest

from reportbuilder.stats.series import Cell, SeriesResult


# ---- Cell.value ------------------------------------------------------------

def test_cell_value_core_fields():
    c = Cell(pct=60.0, count=3.0, mean=2.5)
    assert c.value("pct") == 60.0
    assert c.value("count") == 3.0
    assert c.value("mean") == 2.5


def test_cell_value_extra_lookup():
    c = Cell(pct=None, count=None, mean=None, extra=(("median", 3.0),))
    assert c.value("median") == 3.0


def test_cell_value_unknown_extra_is_none():
    c = Cell(pct=1.0)
    assert c.value("median") is None


# ---- SeriesResult ----------------------------------------------------------

def _series():
    return SeriesResult(
        categories=("Yes", "No"), segments=("Total",),
        cells={("Yes", "Total"): Cell(pct=60.0, count=3.0),
               ("No", "Total"): Cell(pct=40.0, count=2.0)},
        base_n={"Total": 5}, statistic="pct",
    )


def test_cell_accessor_returns_cell():
    assert _series().cell("Yes", "Total").pct == 60.0


def test_cell_accessor_keyerror_on_miss():
    with pytest.raises(KeyError):
        _series().cell("Maybe", "Total")


def test_n_series_single_segment():
    assert _series().n_series == 1


def test_n_series_multiple_segments():
    sr = SeriesResult(categories=("A",), segments=("X", "Y", "Total"),
                      cells={}, base_n={}, statistic="pct")
    assert sr.n_series == 3


# ---- is_partition ----------------------------------------------------------

def test_is_partition_single_choice_counts_sum_to_base():
    assert _series().is_partition() is True


def test_is_partition_multi_overlap_is_false():
    # counts 3+3 = 6 but base 4 -> overlap beyond tolerance
    sr = SeriesResult(
        categories=("A", "B"), segments=("Total",),
        cells={("A", "Total"): Cell(pct=75.0, count=3.0),
               ("B", "Total"): Cell(pct=75.0, count=3.0)},
        base_n={"Total": 4}, statistic="pct",
    )
    assert sr.is_partition() is False


def test_is_partition_pct_fallback_when_counts_absent():
    sr = SeriesResult(
        categories=("A", "B"), segments=("Total",),
        cells={("A", "Total"): Cell(pct=60.0, count=None),
               ("B", "Total"): Cell(pct=40.0, count=None)},
        base_n={"Total": 5}, statistic="pct",
    )
    assert sr.is_partition() is True


def test_is_partition_pct_fallback_not_summing_to_100_is_false():
    sr = SeriesResult(
        categories=("A", "B"), segments=("Total",),
        cells={("A", "Total"): Cell(pct=60.0, count=None),
               ("B", "Total"): Cell(pct=30.0, count=None)},
        base_n={"Total": 5}, statistic="pct",
    )
    assert sr.is_partition() is False


def test_is_partition_first_of_multiple_segments_not_partitioning_is_false():
    # Default segment = segments[0] ("X"); its counts 2+2=4 != base 10
    sr = SeriesResult(
        categories=("A", "B"), segments=("X", "Total"),
        cells={("A", "X"): Cell(count=2.0), ("B", "X"): Cell(count=2.0),
               ("A", "Total"): Cell(count=5.0), ("B", "Total"): Cell(count=5.0)},
        base_n={"X": 10, "Total": 10}, statistic="pct",
    )
    assert sr.is_partition() is False


def test_is_partition_zero_base_is_false():
    sr = SeriesResult(
        categories=("A",), segments=("Total",),
        cells={("A", "Total"): Cell(count=0.0)},
        base_n={"Total": 0}, statistic="pct",
    )
    assert sr.is_partition() is False


def test_is_partition_named_segment():
    sr = SeriesResult(
        categories=("A", "B"), segments=("X", "Total"),
        cells={("A", "X"): Cell(count=3.0), ("B", "X"): Cell(count=2.0),
               ("A", "Total"): Cell(count=3.0), ("B", "Total"): Cell(count=2.0)},
        base_n={"X": 5, "Total": 5}, statistic="pct",
    )
    assert sr.is_partition("X") is True
