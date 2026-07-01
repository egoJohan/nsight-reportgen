"""Unit tests for reportbuilder.stats.statistics (pct/count_value/mean/summary_value)."""
from __future__ import annotations

import math

import pandas as pd
import pytest

from reportbuilder.model.question import Variable
from reportbuilder.model.report import NumberFormat
from reportbuilder.stats import statistics as st  # noqa: F401  (import registers stats)
from reportbuilder.stats.registry import statistic


def _var(missing=()):
    return Variable(name="v", label="v", measurement="scale",
                    value_labels=(), missing_values=frozenset(missing))


# ---- pct -------------------------------------------------------------------

def test_pct_whole_number_default_zero_decimals():
    assert st.pct(3, 5, NumberFormat()) == 60.0


def test_pct_rounds_to_configured_decimals():
    assert st.pct(1, 3, NumberFormat(pct_decimals=1)) == 33.3
    assert st.pct(1, 3, NumberFormat(pct_decimals=2)) == 33.33


def test_pct_zero_decimals_rounds_to_integer():
    # 1/3 -> 33.33.. -> 33 at 0 decimals
    assert st.pct(1, 3, NumberFormat(pct_decimals=0)) == 33.0


def test_pct_zero_base_is_zero_not_error():
    assert st.pct(5, 0, NumberFormat()) == 0.0


def test_pct_full_base():
    assert st.pct(5, 5, NumberFormat()) == 100.0


# ---- count_value -----------------------------------------------------------

def test_count_value_round_to_nearest_default():
    assert st.count_value(2.4, NumberFormat()) == 2.0
    assert st.count_value(2.6, NumberFormat()) == 3.0


def test_count_value_ceil_when_round_up():
    fmt = NumberFormat(count_round_up=True)
    assert st.count_value(2.1, fmt) == 3.0
    assert st.count_value(2.0, fmt) == 2.0
    assert st.count_value(2.1, fmt) == float(math.ceil(2.1))


def test_count_value_returns_float():
    assert isinstance(st.count_value(3, NumberFormat()), float)


# ---- mean ------------------------------------------------------------------

def test_mean_drops_user_missing_and_nan():
    values = pd.Series([1.0, 2.0, 3.0, 9.0, float("nan")])
    # var-missing 9 and NaN dropped -> mean of [1,2,3] = 2.0
    assert st.mean(values, _var(missing=(9.0,)), NumberFormat()) == 2.0


def test_mean_rounds_to_mean_decimals():
    values = pd.Series([1.0, 2.0])
    assert st.mean(values, _var(), NumberFormat(mean_decimals=1)) == 1.5


def test_mean_empty_after_filtering_is_zero():
    values = pd.Series([9.0, 9.0, float("nan")])
    assert st.mean(values, _var(missing=(9.0,)), NumberFormat()) == 0.0


def test_mean_all_empty_series_is_zero():
    assert st.mean(pd.Series([], dtype=float), _var(), NumberFormat()) == 0.0


# ---- summary_value ---------------------------------------------------------

def test_summary_value_median():
    values = pd.Series([10.0, 20.0, 30.0, 40.0, 99.0])
    med = statistic("median")
    # 99 is user-missing -> median of [10,20,30,40] = 25.0
    assert st.summary_value(values, _var(missing=(99.0,)), NumberFormat(), med) == 25.0


def test_summary_value_sum_excludes_missing_and_nan():
    values = pd.Series([10.0, 20.0, 99.0, float("nan")])
    total = statistic("sum")
    assert st.summary_value(values, _var(missing=(99.0,)), NumberFormat(), total) == 30.0


def test_summary_value_empty_is_zero():
    values = pd.Series([float("nan")])
    assert st.summary_value(values, _var(), NumberFormat(), statistic("sum")) == 0.0


# ---- registry (populated by importing statistics) --------------------------

@pytest.mark.parametrize("name,family", [
    ("pct", "distribution"),
    ("count", "distribution"),
    ("mean", "summary"),
    ("median", "summary"),
    ("sum", "summary"),
])
def test_builtin_statistics_resolve(name, family):
    s = statistic(name)
    assert s.name == name
    assert s.family == family


def test_distribution_stats_have_cell_fn_summary_have_summary_fn():
    assert statistic("pct").cell_fn is not None
    assert statistic("pct").summary_fn is None
    assert statistic("mean").summary_fn is not None
    assert statistic("mean").cell_fn is None


def test_unknown_statistic_raises_keyerror_listing_registered():
    with pytest.raises(KeyError) as ei:
        statistic("bogus")
    msg = str(ei.value)
    assert "bogus" in msg
    # the error lists the registered statistic names
    for name in ("pct", "count", "mean", "median", "sum"):
        assert name in msg
