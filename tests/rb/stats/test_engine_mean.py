"""Tests for stats/engine.py — mean statistic path. TDD: tests written first.

REQ-C-15 (mean of scale and categorical-with-codes variables),
REQ-N-02 (missing-value exclusion for mean),
REQ-C-14 (per-segment means with classifying variable).
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fidelity import numbers_from_pptx


# ---------------------------------------------------------------------------
# Helper: build a mean ChartSpec with sensible defaults
# ---------------------------------------------------------------------------

def _mean_spec(qref: str, **kw) -> ChartSpec:
    return ChartSpec(
        question_ref=qref,
        chart_type=kw.get("chart_type", "vertical_bar"),
        statistic="mean",
        classifying_var=kw.get("classifying_var", None),
        number_format=kw.get("number_format", NumberFormat()),
        sort=kw.get("sort", SortSpec(basis="data_order")),
        template_slot=kw.get("template_slot", "s1"),
        elements=kw.get("elements", ElementToggles()),
    )


# ---------------------------------------------------------------------------
# Test 1: Scale variable, no classifier — pure scale mean
# ---------------------------------------------------------------------------

def test_mean_scale_no_classifier():
    """Scale variable (measurement=scale, no value labels) produces one-category
    mean SeriesResult. REQ-C-15, REQ-N-02."""
    var = Variable(
        name="age",
        label="Age",
        measurement="scale",
        value_labels=(),
        missing_values=frozenset(),
    )
    q = Question(qid="age", kind="single", variables=("age",), text="Age")
    model = QuestionModel(variables={"age": var}, questions=[q])
    df = pd.DataFrame({"age": [30.0, 40.0, 50.0, 60.0, 70.0]})

    res = compute(q, _mean_spec("age"), df, model)

    assert res.categories == ("Age",)
    assert res.segments == ("Total",)
    assert res.cell("Age", "Total").mean == 50.0
    assert res.cell("Age", "Total").pct is None
    assert res.cell("Age", "Total").count is None
    assert res.statistic == "mean"
    assert res.base_n["Total"] == 5


# ---------------------------------------------------------------------------
# Test 2: Categorical with numeric codes (mean-Likert)
# ---------------------------------------------------------------------------

def test_mean_categorical_with_codes():
    """Categorical variable with codes 1..5 — mean is computed over numeric codes.
    REQ-C-15."""
    var = Variable(
        name="rating",
        label="Rating",
        measurement="categorical",
        value_labels=(
            ValueLabel(1.0, "Very Poor"),
            ValueLabel(2.0, "Poor"),
            ValueLabel(3.0, "Neutral"),
            ValueLabel(4.0, "Good"),
            ValueLabel(5.0, "Very Good"),
        ),
        missing_values=frozenset(),
    )
    q = Question(qid="rating", kind="single", variables=("rating",), text="Rating")
    model = QuestionModel(variables={"rating": var}, questions=[q])
    # [1,1,1,2,2] -> mean = 7/5 = 1.4
    df = pd.DataFrame({"rating": [1.0, 1.0, 1.0, 2.0, 2.0]})

    res = compute(q, _mean_spec("rating"), df, model)

    assert res.categories == ("Rating",)
    assert res.segments == ("Total",)
    # mean_decimals=1 by default: round(1.4, 1) == 1.4
    assert res.cell("Rating", "Total").mean == 1.4
    assert res.statistic == "mean"


# ---------------------------------------------------------------------------
# Test 3: Mean with a classifying variable — per-segment means
# ---------------------------------------------------------------------------

def test_mean_with_classifying_var():
    """Per-segment means + Total. REQ-C-14, REQ-C-15.

    classifier (gender): 1=Male, 2=Female
    scores: [3, 5, 4, 2] with genders [1, 1, 2, 2]
    Male mean = (3+5)/2 = 4.0; Female mean = (4+2)/2 = 3.0; Total = (3+5+4+2)/4 = 3.5
    """
    var = Variable(
        name="score",
        label="Score",
        measurement="scale",
        value_labels=(),
        missing_values=frozenset(),
    )
    q = Question(qid="score", kind="single", variables=("score",), text="Score")
    model = QuestionModel(variables={"score": var}, questions=[q])

    df = pd.DataFrame({
        "score": [3.0, 5.0, 4.0, 2.0],
        "gender": [1.0, 1.0, 2.0, 2.0],
    })

    res = compute(q, _mean_spec("score", classifying_var="gender"), df, model)

    assert res.statistic == "mean"
    assert res.categories == ("Score",)
    # segments: classifier codes "1","2" then "Total"
    assert "1" in res.segments
    assert "2" in res.segments
    assert "Total" in res.segments

    assert res.cell("Score", "1").mean == 4.0
    assert res.cell("Score", "2").mean == 3.0
    assert res.cell("Score", "Total").mean == 3.5

    assert res.base_n["1"] == 2
    assert res.base_n["2"] == 2
    assert res.base_n["Total"] == 4


# ---------------------------------------------------------------------------
# Test 4: Missing-value handling — user-missing codes excluded from mean
# ---------------------------------------------------------------------------

def test_mean_excludes_missing_values():
    """User-missing codes and NaN are excluded from the mean computation. REQ-N-02."""
    var = Variable(
        name="sat",
        label="Satisfaction",
        measurement="categorical",
        value_labels=(
            ValueLabel(1.0, "Low"),
            ValueLabel(2.0, "Mid"),
            ValueLabel(3.0, "High"),
            ValueLabel(99.0, "DK"),
        ),
        missing_values=frozenset({99.0}),
    )
    q = Question(qid="sat", kind="single", variables=("sat",), text="Satisfaction")
    model = QuestionModel(variables={"sat": var}, questions=[q])

    import numpy as np
    # valid values: [1, 2, 3] → mean = 2.0; 99 and NaN should be excluded
    df = pd.DataFrame({"sat": [1.0, 2.0, 3.0, 99.0, float("nan")]})

    res = compute(q, _mean_spec("sat"), df, model)

    assert res.cell("Satisfaction", "Total").mean == 2.0
    assert res.base_n["Total"] == 3   # only 3 valid values


# ---------------------------------------------------------------------------
# Test 5: Renders through a bar chart (light integration)
# ---------------------------------------------------------------------------

def test_mean_renders_through_bar_chart(tmp_path):
    """Build a 1-ChartSpec Report (bar, mean) over a scale variable and verify
    the output PPTX contains the computed mean value. REQ-C-15, REQ-N-02."""
    var = Variable(
        name="age",
        label="Age",
        measurement="scale",
        value_labels=(),
        missing_values=frozenset(),
    )
    q = Question(qid="age", kind="single", variables=("age",), text="Age")
    model = QuestionModel(variables={"age": var}, questions=[q])
    df = pd.DataFrame({"age": [30.0, 40.0, 50.0, 60.0, 70.0]})
    # expected mean = 50.0

    spec = ChartSpec(
        question_ref="age",
        chart_type="vertical_bar",
        statistic="mean",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="s1",
        elements=ElementToggles(),
    )
    report = Report(
        name="MeanTest",
        render_mode="native",
        template_ref="t.pptx",
        charts=(spec,),
    )

    out = str(tmp_path / "mean_test.pptx")
    result_path = build_pptx(report, model, df, out)
    assert os.path.exists(result_path)

    extracted = numbers_from_pptx(result_path)
    pool: list[float] = []
    for v in extracted.values():
        pool.extend(v if isinstance(v, (list, tuple)) else [v])
    expected_mean = 50.0
    assert any(abs(expected_mean - got) <= 0.5 for got in pool), (
        f"Expected mean ~{expected_mean} not found in PPTX values: {pool}"
    )
