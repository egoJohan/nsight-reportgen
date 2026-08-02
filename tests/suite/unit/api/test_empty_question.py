"""A question whose columns hold no answers at all cannot be charted.

The Erisan material carries two such columns — var319 ("m") and var320 ("p"),
0 answers out of 511 — which were offered like any other question and produced
blank slides. Only "no variables" used to make a question non-chartable.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.api import routes_questions as R
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable


def _model(**cols):
    vars_ = {
        n: Variable(name=n, label=n, measurement="categorical",
                    value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
                    missing_values=frozenset())
        for n in cols
    }
    return QuestionModel(variables=vars_, questions=[]), pd.DataFrame(cols)


def test_a_question_with_no_answers_is_not_chartable():
    model, df = _model(q=[None, None, None])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    ok, reason = R._question_chartable(model, q, df)
    assert ok is False
    assert reason and "answer" in reason.lower()


def test_blank_strings_do_not_count_as_answers():
    """var319/var320 are empty STRINGS, not nulls."""
    model, df = _model(q=["", "   ", ""])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    assert R._question_chartable(model, q, df)[0] is False


def test_a_question_with_answers_is_chartable():
    model, df = _model(q=[1.0, 2.0, None])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    assert R._question_chartable(model, q, df) == (True, None)


def test_a_multi_is_chartable_when_any_member_has_answers():
    model, df = _model(a=[None, None], b=[1.0, None])
    q = Question(qid="m", kind="multi", variables=("a", "b"), text="M")
    assert R._question_chartable(model, q, df)[0] is True


def test_a_multi_with_no_answers_anywhere_is_not_chartable():
    model, df = _model(a=[None, None], b=[None, None])
    q = Question(qid="m", kind="multi", variables=("a", "b"), text="M")
    assert R._question_chartable(model, q, df)[0] is False


def test_without_data_the_old_answer_is_kept():
    """The check is skipped when no DataFrame is available, so callers that have
    only a model behave exactly as before."""
    model, _df = _model(q=[None, None])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    assert R._question_chartable(model, q) == (True, None)


def test_a_question_with_no_variables_is_still_not_chartable():
    model, df = _model(q=[1.0])
    q = Question(qid="x", kind="single", variables=(), text="X")
    assert R._question_chartable(model, q, df)[0] is False
