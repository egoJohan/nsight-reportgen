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


# ---- is_partition(undershoot_tol=...) — offering-side asymmetric allowance -
#
# An audit of the store's saved partition-assuming charts found three real
# populations behind a non-strict-partition pie/doughnut:
#   1. genuine multi-response overlap (462%, 800% of base)          -> a real defect
#   2. two answer codes merged onto one display label (104% of base) -> also wrong
#   3. ~50 single-choice questions missing a tiny "no answer" slice
#      (98-99.8% of base)                                            -> harmless
# `undershoot_tol` must keep offering pie for population 3 while leaving
# populations 1 and 2 excluded exactly as the strict default already does.

def test_undershoot_tol_default_none_keeps_strict_symmetric_behavior():
    """No undershoot_tol given -> identical to the plain is_partition() default
    (a caller that doesn't ask for the wider allowance never gets it silently)."""
    sr = SeriesResult(
        categories=("A", "B"), segments=("Total",),
        cells={("A", "Total"): Cell(pct=60.0, count=97.0),
               ("B", "Total"): Cell(pct=37.0, count=60.0)},
        base_n={"Total": 160}, statistic="pct",  # 98% of base — 2% short
    )
    assert sr.is_partition() is False
    assert sr.is_partition(undershoot_tol=None) is False


def test_undershoot_tol_keeps_pie_for_small_no_answer_shortfall():
    """Population 3: a few excluded non-respondents still counted in the base
    (98-99.8% of base) — must remain a partition for offering purposes."""
    for pct_of_base in (0.998, 0.99, 0.982):  # down to ~1.8% short
        base = 1000
        count = round(base * pct_of_base)
        sr = SeriesResult(
            categories=("A",), segments=("Total",),
            cells={("A", "Total"): Cell(pct=100 * count / base, count=float(count))},
            base_n={"Total": base}, statistic="pct",
        )
        assert sr.is_partition(undershoot_tol=3.0) is True, pct_of_base


def test_undershoot_tol_does_not_loosen_overshoot_side():
    """Population 1 (multi-response overlap, 462%/800% analogues) stays
    excluded — undershoot_tol never grants overshoot slack."""
    for total_pct in (462.0, 800.0):
        sr = SeriesResult(
            categories=("A", "B"), segments=("Total",),
            cells={("A", "Total"): Cell(pct=total_pct / 2, count=total_pct / 2),
                   ("B", "Total"): Cell(pct=total_pct / 2, count=total_pct / 2)},
            base_n={"Total": 100}, statistic="pct",
        )
        assert sr.is_partition(undershoot_tol=3.0) is False, total_pct


def test_undershoot_tol_excludes_merged_label_overshoot():
    """Population 2: two codes merged onto one label -> shares sum to 104% of
    base — an overshoot, so it stays excluded even with undershoot_tol set."""
    sr = SeriesResult(
        categories=("A", "B"), segments=("Total",),
        cells={("A", "Total"): Cell(pct=60.0, count=60.0),
               ("B", "Total"): Cell(pct=44.0, count=44.0)},
        base_n={"Total": 100}, statistic="pct",
    )
    assert sr.is_partition(undershoot_tol=3.0) is False


def test_undershoot_tol_still_rejects_shortfall_beyond_the_allowance():
    """A shortfall well beyond the observed real-world worst case (2%) is not
    silently swallowed by a generous undershoot_tol."""
    sr = SeriesResult(
        categories=("A",), segments=("Total",),
        cells={("A", "Total"): Cell(pct=80.0, count=80.0)},
        base_n={"Total": 100}, statistic="pct",  # 20% short
    )
    assert sr.is_partition(undershoot_tol=3.0) is False


def test_undershoot_tol_scales_with_base_not_absolute_count():
    """undershoot_tol is percent-of-base, so it behaves the same on a small and
    a large sample (a flat absolute count tolerance would not)."""
    small = SeriesResult(
        categories=("A",), segments=("Total",),
        cells={("A", "Total"): Cell(pct=99.0, count=99.0)},
        base_n={"Total": 100}, statistic="pct",  # 1 short = 1%
    )
    large = SeriesResult(
        categories=("A",), segments=("Total",),
        cells={("A", "Total"): Cell(pct=99.0, count=9900.0)},
        base_n={"Total": 10000}, statistic="pct",  # 100 short = 1%
    )
    assert small.is_partition(undershoot_tol=3.0) is True
    assert large.is_partition(undershoot_tol=3.0) is True
