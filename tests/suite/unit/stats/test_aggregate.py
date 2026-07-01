"""Unit tests for reportbuilder.stats.aggregate.aggregate_counts."""
from __future__ import annotations

import pandas as pd

from reportbuilder.stats.aggregate import aggregate_counts


def test_total_only_counts_per_value():
    df = pd.DataFrame({"v": [1.0, 1.0, 1.0, 2.0, 2.0]})
    counts = aggregate_counts(df, "v")
    assert counts == {(1.0, "Total"): 3, (2.0, "Total"): 2}


def test_null_value_rows_excluded():
    df = pd.DataFrame({"v": [1.0, 2.0, None, None]})
    counts = aggregate_counts(df, "v")
    assert counts == {(1.0, "Total"): 1, (2.0, "Total"): 1}
    # NULLs contribute no key
    assert all(k[0] is not None for k in counts)


def test_with_classifier_adds_per_value_segment_and_keeps_total():
    df = pd.DataFrame({"v": [1.0, 1.0, 2.0], "g": [1, 2, 1]})
    counts = aggregate_counts(df, "v", "g")
    # Total always present per value
    assert counts[(1.0, "Total")] == 2
    assert counts[(2.0, "Total")] == 1
    # per-(value, segment) with integer-string labels
    assert counts[(1.0, "1")] == 1
    assert counts[(1.0, "2")] == 1
    assert counts[(2.0, "1")] == 1


def test_classifier_null_rows_excluded_from_segment_counts():
    df = pd.DataFrame({"v": [1.0, 1.0], "g": [1, None]})
    counts = aggregate_counts(df, "v", "g")
    # Total counts both; segment counts only the classified row
    assert counts[(1.0, "Total")] == 2
    assert counts[(1.0, "1")] == 1
    assert (1.0, "None") not in counts


def test_non_integer_classifier_code_label_path():
    df = pd.DataFrame({"v": [1.0, 1.0, 2.0], "g": [1.5, 1.5, 2.0]})
    counts = aggregate_counts(df, "v", "g")
    # non-integer classifier code -> str(code) "1.5"; integer -> "2"
    assert counts[(1.0, "1.5")] == 2
    assert counts[(2.0, "2")] == 1
