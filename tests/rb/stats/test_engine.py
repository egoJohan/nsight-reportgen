"""Tests for stats/engine.py — compute() orchestrates aggregate+base+statistics+sort
into a SeriesResult. TDD: tests written before implementation exists.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    SortSpec,
)
from reportbuilder.stats.engine import compute


# ---------------------------------------------------------------------------
# Helper: build a ChartSpec with sensible defaults, overridable via kwargs
# ---------------------------------------------------------------------------

def _spec(qref: str, **kw) -> ChartSpec:
    return ChartSpec(
        question_ref=qref,
        chart_type=kw.get("chart_type", "vertical_bar"),
        statistic=kw.get("statistic", "pct"),
        classifying_var=kw.get("classifying_var", None),
        number_format=kw.get("number_format", NumberFormat()),
        sort=kw.get("sort", SortSpec(basis="pct")),
        template_slot=kw.get("template_slot", "s1"),
        elements=kw.get("elements", ElementToggles()),
    )


# ---------------------------------------------------------------------------
# Fixtures: shared model and question objects
# ---------------------------------------------------------------------------

@pytest.fixture()
def single_model() -> QuestionModel:
    var = Variable(
        name="q1",
        label="Overall satisfaction",
        measurement="categorical",
        value_labels=(
            ValueLabel(1.0, "Poor"),
            ValueLabel(2.0, "Good"),
            ValueLabel(99.0, "DK"),
        ),
        missing_values=frozenset({99.0}),
    )
    q = Question(qid="q1", kind="single", variables=("q1",), text="Overall satisfaction")
    return QuestionModel(variables={"q1": var}, questions=[q])


@pytest.fixture()
def multi_model() -> QuestionModel:
    m1 = Variable(
        name="m1",
        label="Brand A",
        measurement="categorical",
        value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
        missing_values=frozenset(),
    )
    m2 = Variable(
        name="m2",
        label="Brand B",
        measurement="categorical",
        value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
        missing_values=frozenset(),
    )
    q = Question(qid="brands", kind="multi", variables=("m1", "m2"), text="Which brands?")
    return QuestionModel(variables={"m1": m1, "m2": m2}, questions=[q])


# ---------------------------------------------------------------------------
# Test 1: single question — excludes missing codes + NaN, sorts by pct desc
# ---------------------------------------------------------------------------

def test_single_pct_excludes_missing_and_sorts_by_pct(single_model):
    """compute() on a single question:
    - excludes user-missing code (99) and NaN from both counts and base
    - base_n["Total"] == 4  (rows with value 1 or 2 only)
    - categories sorted descending by pct: ("Good", "Poor")
    - Good pct == 75.0 (3 of 4), Poor pct == 25.0 (1 of 4)
    - statistic propagated from spec
    """
    df = pd.DataFrame({"q1": [1.0, 2.0, 2.0, 2.0, 99.0, np.nan]})
    q = single_model.question("q1")

    res = compute(q, _spec("q1"), df, single_model)

    assert res.segments == ("Total",)
    assert res.base_n["Total"] == 4
    assert res.categories == ("Good", "Poor")
    assert res.cell("Good", "Total").pct == 75.0
    assert res.cell("Poor", "Total").pct == 25.0
    assert res.statistic == "pct"


# ---------------------------------------------------------------------------
# Test 2: multi question — base = respondents answering (>=1 valid selection)
# ---------------------------------------------------------------------------

def test_multi_base_is_respondents_answering(multi_model):
    """compute() on a multi question:
    - base = respondents who answered (value==1 on at least one member)
      row 0: m1=1 → answered; row 1: m2=1 → answered; row 2: neither → not
      base_n["Total"] == 2
    - Brand A: 1 of 2 respondents selected → 50.0%
    - Brand B: 2 of 2 respondents selected → 100.0%
    - data_order sort preserves Brand A before Brand B
    """
    df = pd.DataFrame({"m1": [1.0, 0.0, 0.0], "m2": [1.0, 1.0, 0.0]})
    q = multi_model.question("brands")

    res = compute(q, _spec("brands", sort=SortSpec(basis="data_order")), df, multi_model)

    assert res.base_n["Total"] == 2
    assert res.cell("Brand A", "Total").pct == 50.0
    assert res.cell("Brand B", "Total").pct == 100.0
