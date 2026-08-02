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
    # The null-classifier row is in NO segment, so it counts towards neither the
    # segments nor the Total — the Total must stay on the same population as the
    # segment bases. (Before 2026-08-02 the Total counted it, asserting 2 here and
    # letting the Total column's percentages exceed 100%.)
    assert counts[(1.0, "Total")] == 1
    assert counts[(1.0, "1")] == 1
    assert (1.0, "None") not in counts


def test_non_integer_classifier_code_label_path():
    df = pd.DataFrame({"v": [1.0, 1.0, 2.0], "g": [1.5, 1.5, 2.0]})
    counts = aggregate_counts(df, "v", "g")
    # non-integer classifier code -> str(code) "1.5"; integer -> "2"
    assert counts[(1.0, "1.5")] == 2
    assert counts[(2.0, "2")] == 1


# ---- Total sits on the same population as the segment bases ----------------
# Regression (spec 2026-08-02 §0): the Total used to count ALL rows while
# base_rules.segment_bases counted only segmented rows, so a classifier covering
# 60% of the sample made the Total column's percentages sum to 167%.

def test_total_excludes_rows_outside_every_segment():
    df = pd.DataFrame({
        "q":   [1.0, 2.0] * 50,
        "clf": [1.0] * 30 + [2.0] * 30 + [float("nan")] * 40,
    })
    counts = aggregate_counts(df, "q", "clf")
    # 60 covered rows, alternating q -> 30 each
    assert counts[(1.0, "Total")] == 30
    assert counts[(2.0, "Total")] == 30
    assert counts[(1.0, "Total")] + counts[(2.0, "Total")] == 60


def test_total_unchanged_when_classifier_covers_everyone():
    """The regression guard for every existing cross-tab."""
    df = pd.DataFrame({"q": [1.0, 2.0] * 50, "clf": [1.0] * 50 + [2.0] * 50})
    counts = aggregate_counts(df, "q", "clf")
    assert counts[(1.0, "Total")] == 50
    assert counts[(2.0, "Total")] == 50


def test_total_counts_all_rows_when_there_is_no_classifier():
    df = pd.DataFrame({"q": [1.0, 2.0] * 50})
    counts = aggregate_counts(df, "q")
    assert counts[(1.0, "Total")] == 50
    assert counts[(2.0, "Total")] == 50
