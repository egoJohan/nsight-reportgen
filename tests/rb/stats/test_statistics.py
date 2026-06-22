"""Tests for statistics.py — pct, count_value, mean. (REQ-N-01/02/03, REQ-C-15)"""
from __future__ import annotations
import pandas as pd
import pytest
from reportbuilder.model.question import Variable
from reportbuilder.model.report import NumberFormat
from reportbuilder.stats.statistics import count_value, mean, pct


def _fmt(**kw) -> NumberFormat:
    return NumberFormat(**kw)


_SCALE_VAR = Variable(
    name="age",
    label="Age",
    measurement="scale",
    value_labels=(),
    missing_values=frozenset({99.0}),
)


# ---------------------------------------------------------------------------
# pct
# ---------------------------------------------------------------------------

def test_pct_whole_default():
    assert pct(43.0, 100, _fmt()) == 43.0
    assert pct(1.0, 3, _fmt()) == 33.0   # 0 decimals by default → 33


def test_pct_configurable_decimals():
    assert pct(1.0, 3, _fmt(pct_decimals=1)) == 33.3
    assert pct(1.0, 3, _fmt(pct_decimals=2)) == 33.33


def test_pct_zero_base():
    assert pct(5.0, 0, _fmt()) == 0.0


# ---------------------------------------------------------------------------
# count_value
# ---------------------------------------------------------------------------

def test_count_round_up_vs_nearest():
    """Counts are whole numbers; configurable round-up supported. (REQ-N-03)"""
    assert count_value(4.2, _fmt()) == 4.0            # round-to-nearest
    assert count_value(4.2, _fmt(count_round_up=True)) == 5.0   # ceil
    assert count_value(4.0, _fmt(count_round_up=True)) == 4.0   # ceil of whole number
    assert isinstance(count_value(4.2, _fmt()), float)


# ---------------------------------------------------------------------------
# mean
# ---------------------------------------------------------------------------

def test_mean_excludes_missing_and_decimals():
    """Means are shown with configurable decimal format; missing excluded. (REQ-N-02)"""
    s = pd.Series([10.0, 20.0, 99.0, 30.0])
    # 99.0 is a missing value → mean of {10, 20, 30} = 20.0
    assert mean(s, _SCALE_VAR, _fmt(mean_decimals=1)) == 20.0
    assert mean(s, _SCALE_VAR, _fmt(mean_decimals=2)) == 20.0


def test_mean_empty_series():
    """Empty series should return 0.0."""
    assert mean(pd.Series([], dtype=float), _SCALE_VAR, _fmt()) == 0.0


def test_mean_nan_only_series():
    """Series with only NaN values should return 0.0."""
    assert mean(
        pd.Series([float("nan"), float("nan")]),
        _SCALE_VAR,
        _fmt(),
    ) == 0.0
