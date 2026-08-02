"""Mask-based segmentation: one boolean mask per segment, so segments may overlap.

`seg_series` holds one key per row and structurally cannot express a respondent
belonging to two segments. (spec 2026-08-02 §2.3)
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import ValueLabel, Variable
from reportbuilder.stats.aggregate import aggregate_counts
from reportbuilder.stats.base_rules import segment_bases


def _var():
    return Variable(name="q", label="Q", measurement="categorical",
                    value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
                    missing_values=frozenset())


def _df(n=100):
    return pd.DataFrame({"q": [1.0, 2.0] * (n // 2)})


def test_disjoint_masks_match_the_seg_series_path():
    """The guarantee that existing classifiers are untouched."""
    df = _df()
    keys = pd.Series(["A"] * 50 + ["B"] * 50, index=df.index)
    masks = {"A": keys == "A", "B": keys == "B"}
    assert segment_bases(df, _var(), seg_masks=masks) == \
           segment_bases(df, _var(), seg_series=keys)
    assert aggregate_counts(df, "q", seg_masks=masks) == \
           aggregate_counts(df, "q", seg_series=keys)


def test_overlapping_masks_get_independent_bases():
    df = _df()
    masks = {"A": pd.Series([True] * 60 + [False] * 40, index=df.index),
             "B": pd.Series([False] * 40 + [True] * 60, index=df.index)}
    bases = segment_bases(df, _var(), seg_masks=masks)
    assert bases["A"] == 60
    assert bases["B"] == 60
    assert bases["Total"] == 100           # the union, not the sum
    assert bases["A"] + bases["B"] > bases["Total"]


def test_total_excludes_rows_in_no_segment():
    """A screened design: 40 respondents saw nothing."""
    df = _df()
    masks = {"A": pd.Series([True] * 30 + [False] * 70, index=df.index),
             "B": pd.Series([False] * 30 + [True] * 30 + [False] * 40, index=df.index)}
    bases = segment_bases(df, _var(), seg_masks=masks)
    assert bases["Total"] == 60
    counts = aggregate_counts(df, "q", seg_masks=masks)
    assert counts[(1.0, "Total")] + counts[(2.0, "Total")] == 60


def test_counts_are_per_mask():
    df = _df()
    masks = {"A": pd.Series([True] * 50 + [False] * 50, index=df.index),
             "B": pd.Series([False] * 50 + [True] * 50, index=df.index)}
    counts = aggregate_counts(df, "q", seg_masks=masks)
    assert counts[(1.0, "A")] == 25
    assert counts[(2.0, "B")] == 25


def test_overlapping_counts_are_per_mask_not_split():
    """A respondent in both segments counts once in EACH — that is the point."""
    df = _df(4)
    masks = {"A": pd.Series([True, True, False, False], index=df.index),
             "B": pd.Series([True, True, True, True], index=df.index)}
    counts = aggregate_counts(df, "q", seg_masks=masks)
    assert counts[(1.0, "A")] == 1          # rows 0,1 -> q = 1.0, 2.0
    assert counts[(1.0, "B")] == 2          # rows 0,2 -> q = 1.0
    assert counts[(1.0, "Total")] == 2      # the union counts each row once


def test_rows_missing_the_measured_question_are_excluded():
    df = pd.DataFrame({"q": [1.0, None, 2.0, None]})
    masks = {"A": pd.Series([True, True, False, False], index=df.index),
             "B": pd.Series([False, False, True, True], index=df.index)}
    bases = segment_bases(df, _var(), seg_masks=masks)
    assert bases["A"] == 1 and bases["B"] == 1 and bases["Total"] == 2
