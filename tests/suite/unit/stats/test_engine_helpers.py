"""Unit tests for engine helper functions.

Covers _relabel_segments, _auto_pct_decimals, _effective_missing, _rating_scale.
"""
from __future__ import annotations

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.stats import engine
from reportbuilder.stats.series import Cell, SeriesResult


def _spec(**kw):
    base = dict(question_ref="v", chart_type="vertical_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


# ---- _relabel_segments -----------------------------------------------------

def test_relabel_segments_maps_codes_to_value_labels():
    seg_var = Variable("grp", "Group", "categorical",
                       (ValueLabel(1.0, "Young"), ValueLabel(2.0, "Old")), frozenset())
    model = QuestionModel(variables={"grp": seg_var}, questions=[])
    res = SeriesResult(
        categories=("A",), segments=("1", "2", "Total"),
        cells={("A", "1"): Cell(pct=1.0), ("A", "2"): Cell(pct=2.0),
               ("A", "Total"): Cell(pct=3.0)},
        base_n={"1": 1, "2": 2, "Total": 3}, statistic="pct",
    )
    out = engine._relabel_segments(res, model, "grp")
    assert out.segments == ("Young", "Old", "Total")
    assert out.base_n == {"Young": 1, "Old": 2, "Total": 3}
    assert out.cell("A", "Young").pct == 1.0


def test_relabel_segments_derived_binary_flag():
    # No value labels, label == name, codes {0,1} -> {"1": name, "0": "Muut"}
    flag = Variable("Suosittelijat", "Suosittelijat", "categorical", (), frozenset())
    model = QuestionModel(variables={"Suosittelijat": flag}, questions=[])
    res = SeriesResult(
        categories=("A",), segments=("0", "1", "Total"),
        cells={("A", "0"): Cell(pct=1.0), ("A", "1"): Cell(pct=2.0),
               ("A", "Total"): Cell(pct=3.0)},
        base_n={"0": 1, "1": 2, "Total": 3}, statistic="pct",
    )
    out = engine._relabel_segments(res, model, "Suosittelijat")
    assert set(out.segments) == {"Suosittelijat", "Muut", "Total"}
    assert out.cell("A", "Suosittelijat").pct == 2.0
    assert out.cell("A", "Muut").pct == 1.0


def test_relabel_segments_unknown_var_returns_unchanged():
    model = QuestionModel(variables={}, questions=[])
    res = SeriesResult(categories=("A",), segments=("1", "Total"),
                       cells={("A", "1"): Cell(pct=1.0), ("A", "Total"): Cell(pct=1.0)},
                       base_n={"1": 1, "Total": 1}, statistic="pct")
    assert engine._relabel_segments(res, model, "missing") is res


# ---- _auto_pct_decimals ----------------------------------------------------

def test_auto_pct_decimals_all_large_integers_zero():
    assert engine._auto_pct_decimals([50.0, 30.0, 20.0]) == 0


def test_auto_pct_decimals_integer_fractions_trivial_zero():
    # all integer-valued -> frac_trivial -> 0 even with a small value
    assert engine._auto_pct_decimals([50.0, 5.0, 45.0]) == 0


def test_auto_pct_decimals_small_nonzero_fraction_one():
    assert engine._auto_pct_decimals([9.5, 40.5, 50.0]) == 1


def test_auto_pct_decimals_tight_spread_one():
    assert engine._auto_pct_decimals([9.5, 9.7, 80.8]) == 1


def test_auto_pct_decimals_empty_zero():
    assert engine._auto_pct_decimals([]) == 0


def test_auto_pct_decimals_ignores_none():
    assert engine._auto_pct_decimals([None, 50.0, 30.0, 20.0]) == 0


# ---- _effective_missing ----------------------------------------------------

def test_effective_missing_none_uses_var_missing():
    var = Variable("v", "v", "categorical", (ValueLabel(9.0, "NA"),), frozenset({9.0}))
    assert engine._effective_missing(_spec(not_answered_codes=None), var) == {9.0}


def test_effective_missing_empty_tuple_only_nan():
    var = Variable("v", "v", "categorical", (ValueLabel(9.0, "NA"),), frozenset({9.0}))
    assert engine._effective_missing(_spec(not_answered_codes=()), var) == set()


def test_effective_missing_explicit_value_set():
    var = Variable("v", "v", "categorical", (ValueLabel(9.0, "NA"),), frozenset({9.0}))
    assert engine._effective_missing(_spec(not_answered_codes=(2.0,)), var) == {2.0}


# ---- _rating_scale ---------------------------------------------------------

def test_rating_scale_parses_leading_digit_and_skips_nonnumeric():
    rv = Variable("r", "r", "scale",
                  (ValueLabel(10.0, "5 - Erittäin"), ValueLabel(20.0, "3"),
                   ValueLabel(9.0, "En osaa sanoa")),
                  frozenset({9.0}))
    scale = engine._rating_scale(rv)
    assert scale == {10.0: 5.0, 20.0: 3.0}


def test_rating_scale_excludes_missing_codes():
    rv = Variable("r", "r", "scale",
                  (ValueLabel(1.0, "1"), ValueLabel(2.0, "2"), ValueLabel(3.0, "3")),
                  frozenset({3.0}))
    scale = engine._rating_scale(rv)
    assert 3.0 not in scale
    assert scale == {1.0: 1.0, 2.0: 2.0}
