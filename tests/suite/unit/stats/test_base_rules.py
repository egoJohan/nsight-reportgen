"""Unit tests for reportbuilder.stats.base_rules (single/multi/segment bases)."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Variable
from reportbuilder.stats.base_rules import single_base, multi_base, segment_bases


def _var(name, missing=()):
    return Variable(name=name, label=name, measurement="scale",
                    value_labels=(), missing_values=frozenset(missing))


# ---- single_base -----------------------------------------------------------

def test_single_base_excludes_nan_and_user_missing():
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 9.0, float("nan")]})
    # 9 is user-missing, NaN is sysmis -> 3 valid
    assert single_base(df, _var("v", missing=(9.0,))) == 3


def test_single_base_no_missing_counts_all_non_nan():
    df = pd.DataFrame({"v": [1.0, 2.0, float("nan")]})
    assert single_base(df, _var("v")) == 2


def test_single_base_with_segment_filter():
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0], "g": [1, 1, 2, 2]})
    seg = df["g"] == 1
    assert single_base(df, _var("v"), segment_filter=seg) == 2


def test_single_base_missing_override_replaces_var_missing():
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0]})
    # override treats 2 as missing -> 2 valid rows remain
    assert single_base(df, _var("v"), missing_override={2.0}) == 2


# ---- multi_base ------------------------------------------------------------

def test_multi_base_is_respondents_not_selection_count():
    df = pd.DataFrame({"m1": [1, 0, 1, 0, 1], "m2": [0, 1, 1, 0, 0]})
    v1, v2 = _var("m1"), _var("m2")
    # rows with >=1 selection: 0,1,2,4 -> 4 respondents (NOT 5 selections)
    assert multi_base(df, [v1, v2]) == 4


def test_multi_base_ignores_zero_only_respondents():
    df = pd.DataFrame({"m1": [0, 0], "m2": [0, 0]})
    assert multi_base(df, [_var("m1"), _var("m2")]) == 0


def test_multi_base_excludes_user_missing_selection_codes():
    df = pd.DataFrame({"m1": [1, 9], "m2": [0, 0]})
    v1 = _var("m1", missing=(9.0,))
    # row1 m1==9 is user-missing -> not counted; only row0 answered
    assert multi_base(df, [v1, _var("m2")]) == 1


# ---- segment_bases ---------------------------------------------------------

def test_segment_bases_has_total_and_integer_string_labels_sorted():
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0], "g": [2, 1, 2, 1, 3]})
    bases = segment_bases(df, _var("v"), "g")
    assert bases["Total"] == 5
    # per-code keys are integer strings, sorted by code
    codes = [k for k in bases if k != "Total"]
    assert codes == ["1", "2", "3"]
    assert bases["1"] == 2 and bases["2"] == 2 and bases["3"] == 1


def test_segment_bases_excludes_missing_in_var_and_classifier():
    df = pd.DataFrame({"v": [1.0, 9.0, 3.0, float("nan")],
                       "g": [1, 1, 2, 2]})
    bases = segment_bases(df, _var("v", missing=(9.0,)), "g")
    # valid v rows: idx0 (g1), idx2 (g2). idx1 v-missing, idx3 v-nan
    assert bases["Total"] == 2
    assert bases["1"] == 1
    assert bases["2"] == 1


def test_segment_bases_missing_override():
    df = pd.DataFrame({"v": [1.0, 2.0, 3.0], "g": [1, 1, 2]})
    bases = segment_bases(df, _var("v"), "g", missing_override={1.0})
    # 1 treated as missing -> only idx1 (v=2,g1) and idx2 (v=3,g2)
    assert bases["Total"] == 2
    assert bases["1"] == 1
    assert bases["2"] == 1
