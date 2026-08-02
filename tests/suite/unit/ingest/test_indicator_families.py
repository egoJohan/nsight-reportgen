"""Ungrouped 1-or-missing indicator columns become one multi question, so an export
WITHOUT 0/1 value labels behaves like one with them. (spec 2026-08-02 §2.2)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.ingest.grouping_override import apply_grouping_override
from reportbuilder.ingest.multi_group import suggest_indicator_families
from reportbuilder.model.question import Question, QuestionModel, Variable


def _var(name, label):
    return Variable(name=name, label=label, measurement="categorical",
                    value_labels=(), missing_values=frozenset())


def _model():
    vars_ = {"Polku1": _var("Polku1", "Polku 1"),
             "Polku2": _var("Polku2", "Polku 2"),
             "TOTAL": _var("TOTAL", "Kaikki vastaajat")}
    qs = [Question(qid=n.lower(), kind="single", variables=(n,), text=v.label)
          for n, v in vars_.items()]
    return QuestionModel(variables=vars_, questions=qs)


def _df(n=200):
    half = n // 2
    return pd.DataFrame({
        "Polku1": [1.0] * half + [None] * (n - half),
        "Polku2": [None] * half + [1.0] * (n - half),
        "TOTAL": [1.0] * n,
    })


def test_indicator_family_is_suggested():
    assert suggest_indicator_families(_model(), _df()) == [("Polku1", "Polku2")]


def test_total_alone_is_not_a_family():
    fams = suggest_indicator_families(_model(), _df())
    assert all("TOTAL" not in f for f in fams)


def test_no_dataframe_means_no_suggestion():
    assert suggest_indicator_families(_model(), None) == []


def test_an_overlapping_family_is_not_suggested():
    """A tick-box grid must not become a classifier."""
    df = _df()
    df["Polku2"] = 1.0                       # everyone in both
    assert suggest_indicator_families(_model(), df) == []


def test_grouping_override_creates_the_multi_question():
    m = apply_grouping_override(_model(), {}, df=_df())
    multis = [q for q in m.questions if q.kind == "multi"]
    assert len(multis) == 1
    assert multis[0].variables == ("Polku1", "Polku2")


def test_without_a_dataframe_the_model_is_unchanged():
    m = apply_grouping_override(_model(), {}, df=None)
    assert [q for q in m.questions if q.kind == "multi"] == []


def test_a_forced_single_is_not_regrouped():
    m = apply_grouping_override(_model(), {"singles": ["Polku1"]}, df=_df())
    assert [q for q in m.questions if q.kind == "multi"] == []


def test_already_grouped_members_are_not_resuggested():
    """When the columns carry 0/1 value labels the existing multi detector already
    grouped them; they must not be offered a second time."""
    model = _model()
    grouped = QuestionModel(
        variables=model.variables,
        questions=[Question(qid="polku", kind="multi",
                            variables=("Polku1", "Polku2"), text="Polku")],
    )
    assert suggest_indicator_families(grouped, _df()) == []


# ---- group naming ----------------------------------------------------------
# A banner family's members are "<Stem> <n>", so the common prefix IS the title.
# _group_text normally rejects a single-word stem (a shared question word like
# "Kuinka" makes a useless title), which left the group called "Polku 1".

def test_indicator_family_is_named_after_the_shared_stem():
    m = apply_grouping_override(_model(), {}, df=_df())
    multi = next(q for q in m.questions if q.kind == "multi")
    assert multi.text == "Polku"


def test_a_shared_question_word_is_still_not_used_as_a_title():
    """The guard this relaxes must keep working: labels differing after a common
    question word fall back to the first label, not to 'Kuinka'."""
    from reportbuilder.ingest.multi_group import _group_text

    vars_ = {"a1": _var("a1", "Kuinka hyvin tunnet brändin"),
             "a2": _var("a2", "Kuinka usein ostat tuotetta")}
    model = QuestionModel(variables=vars_, questions=[])
    assert _group_text(model, ("a1", "a2")) == "Kuinka hyvin tunnet brändin"
