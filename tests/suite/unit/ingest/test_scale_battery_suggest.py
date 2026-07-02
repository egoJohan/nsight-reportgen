"""suggest_scale_batteries — runs of >=3 contiguous same-scale single questions."""
from __future__ import annotations

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.ingest.battery_group import suggest_scale_batteries


def _scale(name, sig="imp"):
    labs = {"imp": ["Ei", "Vähän", "Keski", "Paljon", "Erittäin"],
            "agree": ["Eri", "Osin eri", "Neutraali", "Osin samaa", "Samaa"]}[sig]
    return Variable(name=name, label=f"stmt {name}", measurement="scale",
                    value_labels=tuple(ValueLabel(float(i + 1), l) for i, l in enumerate(labs)),
                    missing_values=frozenset())


def _nominal(name):
    return Variable(name=name, label=name, measurement="categorical",
                    value_labels=(ValueLabel(1.0, "M"), ValueLabel(2.0, "F")),
                    missing_values=frozenset())


def _model(vars_):
    return QuestionModel(
        variables={v.name: v for v in vars_},
        questions=[Question(qid=v.name, kind="single", variables=(v.name,), text=v.label)
                   for v in vars_])


def test_run_of_three_same_scale_is_suggested():
    m = _model([_scale("a"), _scale("b"), _scale("c")])
    out = suggest_scale_batteries(m)
    assert len(out) == 1
    members, labels = out[0]
    assert members == ("a", "b", "c")
    assert labels == ("stmt a", "stmt b", "stmt c")


def test_run_of_two_is_not_suggested():
    m = _model([_scale("a"), _scale("b")])
    assert suggest_scale_batteries(m) == []


def test_non_scale_break_splits_runs():
    # a,b,c share a scale; gender breaks; d,e (only 2) do not qualify
    m = _model([_scale("a"), _scale("b"), _scale("c"), _nominal("g"),
                _scale("d"), _scale("e")])
    out = suggest_scale_batteries(m)
    assert [members for members, _ in out] == [("a", "b", "c")]


def test_different_scale_signatures_do_not_merge():
    # 3 imp + 3 agree, contiguous but different signatures → two separate runs
    m = _model([_scale("a"), _scale("b"), _scale("c"),
                _scale("d", "agree"), _scale("e", "agree"), _scale("f", "agree")])
    out = suggest_scale_batteries(m)
    assert [members for members, _ in out] == [("a", "b", "c"), ("d", "e", "f")]


def test_already_grouped_battery_is_not_resuggested():
    """Members already inside a battery question are not single → never re-suggested."""
    vs = [_scale("a"), _scale("b"), _scale("c")]
    m = QuestionModel(
        variables={v.name: v for v in vs},
        questions=[Question(qid="bat", kind="battery", variables=("a", "b", "c"), text="B")])
    assert suggest_scale_batteries(m) == []
