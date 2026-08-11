"""_quick_series must offer pie/doughnut only for genuinely partition-shaped
data — not for every question, which is what the OLD fabricated series did
(every category got count=10.0 summing exactly to a fabricated base, so
`is_partition()` was always True regardless of the real answers).

Root-cause fixture: mat-erisan2's var7 is a 10-option MULTI question where
respondents pick several options (true option shares sum to 465%). Before the
fix, the picker still offered it a pie, which renormalises and prints a wrong
number for every slice (e.g. 85% shown as 18.3%). `_multi_quick_counts` reads
the real member columns (cheap: vectorized boolean masks, no full compute())
so `_quick_series`'s `is_partition()` reflects the true shape.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.api import routes_questions as R
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable


def _multi_var(name: str) -> Variable:
    return Variable(name=name, label=f"Option {name}", measurement="nominal",
                    value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
                    missing_values=frozenset())


def _multi_model(n: int) -> tuple[QuestionModel, tuple[str, ...]]:
    names = tuple(f"opt{i}" for i in range(n))
    variables = {n_: _multi_var(n_) for n_ in names}
    return QuestionModel(variables=variables, questions=[]), names


def _single_model() -> QuestionModel:
    var = Variable(name="q1", label="Satisfaction", measurement="nominal",
                   value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
                   missing_values=frozenset())
    return QuestionModel(variables={"q1": var}, questions=[])


# ---------------------------------------------------------------------------
# A genuinely overlapping multi (var7-shaped): must lose pie/doughnut.
# ---------------------------------------------------------------------------

def test_overlapping_multi_is_not_offered_pie_or_doughnut():
    """Respondents pick several options (clear, non-noise overlap) -> pie and
    doughnut must be hidden from compatible_chart_types."""
    model, names = _multi_model(3)
    q = Question(qid="q", kind="multi", variables=names, text="Q")
    # 6 respondents, most tick 2+ boxes -> shares sum well above the base.
    df = pd.DataFrame({
        "opt0": [1, 1, 1, 1, 0, 0],
        "opt1": [1, 1, 0, 0, 1, 1],
        "opt2": [0, 1, 1, 0, 0, 0],
    })
    series = R._quick_series(q, model, df)
    assert series.is_partition() is False

    compatible = R._compatible_chart_types(q, series)
    assert "pie" not in compatible
    assert "doughnut" not in compatible
    # Bar/stacked types (which don't gate on is_partition) stay offered.
    assert "vertical_bar" in compatible
    assert "stacked_horizontal_bar" in compatible


def test_var7_shaped_overlap_465_percent_loses_pie():
    """A closer analogue of the real defect: 10 options, shares sum to well
    over 100% of the base (respondents pick several skincare/laundry items)."""
    model, names = _multi_model(10)
    q = Question(qid="var7", kind="multi", variables=names, text="Q")
    n_resp = 40
    # Every respondent selects between 3 and 5 of the 10 options (heavy
    # overlap, like a real "select all that apply" shopping list).
    import random
    rng = random.Random(0)
    cols = {n: [0] * n_resp for n in names}
    for row in range(n_resp):
        picks = rng.sample(names, k=rng.randint(3, 5))
        for p in picks:
            cols[p][row] = 1
    df = pd.DataFrame(cols)
    series = R._quick_series(q, model, df)
    assert series.is_partition() is False
    assert "pie" not in R._compatible_chart_types(q, series)
    assert "doughnut" not in R._compatible_chart_types(q, series)


# ---------------------------------------------------------------------------
# A multi where every respondent chose exactly one option: still a partition.
# ---------------------------------------------------------------------------

def test_effectively_single_choice_multi_keeps_pie():
    """Real multi-response data, but no respondent double-ticks -> the shares
    still sum to the base, so it's a genuine partition and must keep pie."""
    model, names = _multi_model(3)
    q = Question(qid="q", kind="multi", variables=names, text="Q")
    df = pd.DataFrame({
        "opt0": [1, 0, 0, 1, 0],
        "opt1": [0, 1, 0, 0, 1],
        "opt2": [0, 0, 1, 0, 0],
    })
    series = R._quick_series(q, model, df)
    assert series.is_partition() is True

    compatible = R._compatible_chart_types(q, series)
    assert "pie" in compatible
    assert "doughnut" in compatible


def test_multi_without_a_dataframe_falls_back_to_fabricated_partition():
    """No df available (e.g. a model-only caller) -> _quick_series keeps the
    old, cheap fabricated shape (always a partition) rather than raising."""
    model, names = _multi_model(3)
    q = Question(qid="q", kind="multi", variables=names, text="Q")
    series = R._quick_series(q, model, None)
    assert series.is_partition() is True


def test_multi_with_missing_columns_falls_back_to_fabricated_partition():
    """The member columns aren't in the given df (e.g. stale grouping) ->
    fall back rather than KeyError."""
    model, names = _multi_model(3)
    q = Question(qid="q", kind="multi", variables=names, text="Q")
    df = pd.DataFrame({"unrelated": [1, 2, 3]})
    series = R._quick_series(q, model, df)
    assert series.is_partition() is True


# ---------------------------------------------------------------------------
# A single-choice question is a partition by construction -> unaffected.
# ---------------------------------------------------------------------------

def test_single_choice_question_is_unaffected_by_the_df_argument():
    """Single-choice categories come from value labels, never member columns
    -> passing a df (even one with unrelated/overlapping data) changes nothing."""
    model = _single_model()
    q = Question(qid="q1", kind="single", variables=("q1",), text="Q1")
    df = pd.DataFrame({"q1": [1.0, 1.0, 2.0, 2.0, 1.0]})

    series_no_df = R._quick_series(q, model, None)
    series_with_df = R._quick_series(q, model, df)
    assert series_no_df.is_partition() is True
    assert series_with_df.is_partition() is True
    assert series_no_df.categories == series_with_df.categories

    compatible = R._compatible_chart_types(q, series_with_df)
    assert "pie" in compatible
    assert "doughnut" in compatible
