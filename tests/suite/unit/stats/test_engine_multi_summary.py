"""Unit tests for engine._multi and engine._summary via compute()."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.stats import engine


def _spec(**kw):
    base = dict(question_ref="q", chart_type="vertical_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def _binvar(name, label, missing=()):
    return Variable(name=name, label=label, measurement="categorical",
                    value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
                    missing_values=frozenset(missing))


# ---- _multi ----------------------------------------------------------------

def test_multi_one_bar_per_member_with_multi_base():
    v1, v2 = _binvar("m1", "Channel A"), _binvar("m2", "Channel B")
    model = QuestionModel(variables={"m1": v1, "m2": v2}, questions=[])
    q = Question(qid="m", kind="multi", variables=("m1", "m2"), text="Multi")
    df = pd.DataFrame({"m1": [1, 0, 1, 0, 1], "m2": [0, 1, 1, 0, 0]})
    r = engine.compute(q, _spec(question_ref="m"), df, model)
    # one category per member variable
    assert r.categories == ("Channel A", "Channel B")
    # base = respondents with >=1 selection (rows 0,1,2,4) = 4
    assert r.base_n == {"Total": 4}
    assert r.cell("Channel A", "Total").count == 3.0
    assert r.cell("Channel A", "Total").pct == 75.0
    assert r.cell("Channel B", "Total").count == 2.0
    assert r.cell("Channel B", "Total").pct == 50.0


def test_multi_selection_counts_exclude_missing_codes():
    v1, v2 = _binvar("m1", "A", missing=(9.0,)), _binvar("m2", "B")
    model = QuestionModel(variables={"m1": v1, "m2": v2}, questions=[])
    q = Question(qid="m", kind="multi", variables=("m1", "m2"), text="Multi")
    df = pd.DataFrame({"m1": [1, 9, 1], "m2": [0, 1, 0]})
    r = engine.compute(q, _spec(question_ref="m"), df, model)
    # A: only rows 0 and 2 are valid 1s (row1 is 9)
    assert r.cell("A", "Total").count == 2.0


# ---- _summary --------------------------------------------------------------

def _scalevar(missing=()):
    return Variable(name="age", label="Age", measurement="scale",
                    value_labels=(), missing_values=frozenset(missing))


def _model_age(var):
    return (QuestionModel(variables={"age": var}, questions=[]),
            Question(qid="age", kind="single", variables=("age",), text="Age"))


def test_summary_mean_stored_in_mean_field():
    var = _scalevar(missing=(99.0,))
    model, q = _model_age(var)
    df = pd.DataFrame({"age": [10.0, 20, 30, 40, 99]})
    r = engine.compute(q, _spec(question_ref="age", statistic="mean"), df, model)
    assert r.statistic == "mean"
    assert r.categories == ("Age",)
    assert r.segments == ("Total",)
    cell = r.cell("Age", "Total")
    assert cell.mean == 25.0
    assert cell.extra == ()


def test_summary_median_stored_in_extra():
    var = _scalevar(missing=(99.0,))
    model, q = _model_age(var)
    df = pd.DataFrame({"age": [10.0, 20, 30, 40, 99]})
    r = engine.compute(q, _spec(question_ref="age", statistic="median"), df, model)
    cell = r.cell("Age", "Total")
    # non-mean summary stats go into extra, retrievable via .value()
    assert cell.mean is None
    assert cell.value("median") == 25.0
    assert dict(cell.extra) == {"median": 25.0}


def test_summary_sum_stored_in_extra():
    var = _scalevar()
    model, q = _model_age(var)
    df = pd.DataFrame({"age": [10.0, 20, 30]})
    r = engine.compute(q, _spec(question_ref="age", statistic="sum"), df, model)
    assert r.cell("Age", "Total").value("sum") == 60.0


def test_summary_base_is_single_base():
    var = _scalevar(missing=(99.0,))
    model, q = _model_age(var)
    df = pd.DataFrame({"age": [10.0, 20, 99, float("nan")]})
    r = engine.compute(q, _spec(question_ref="age", statistic="mean"), df, model)
    assert r.base_n["Total"] == 2


def test_summary_with_classifier_segments_and_per_segment_means():
    var = _scalevar()
    seg = Variable(name="grp", label="grp", measurement="categorical",
                   value_labels=(), missing_values=frozenset())
    model = QuestionModel(variables={"age": var, "grp": seg}, questions=[])
    q = Question(qid="age", kind="single", variables=("age",), text="Age")
    df = pd.DataFrame({"age": [10.0, 20, 30, 40], "grp": [1, 1, 2, 2]})
    r = engine.compute(q, _spec(question_ref="age", statistic="mean",
                                classifying_var="grp"), df, model)
    assert r.segments == ("1", "2", "Total")
    assert r.cell("Age", "1").mean == 15.0
    assert r.cell("Age", "2").mean == 35.0
    assert r.cell("Age", "Total").mean == 25.0
    assert r.base_n == {"1": 2, "2": 2, "Total": 4}


def test_summary_median_with_classifier_uses_extra():
    var = _scalevar()
    seg = Variable(name="grp", label="grp", measurement="categorical",
                   value_labels=(), missing_values=frozenset())
    model = QuestionModel(variables={"age": var, "grp": seg}, questions=[])
    q = Question(qid="age", kind="single", variables=("age",), text="Age")
    df = pd.DataFrame({"age": [10.0, 20, 30, 40], "grp": [1, 1, 2, 2]})
    r = engine.compute(q, _spec(question_ref="age", statistic="median",
                                classifying_var="grp"), df, model)
    assert r.cell("Age", "1").value("median") == 15.0
    assert r.cell("Age", "2").value("median") == 35.0
