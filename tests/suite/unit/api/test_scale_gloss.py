"""`_scale_gloss` — the endpoint gloss the questions API offers the frontend so the
Design → Subtitle box prefills with the exact line a stacked bar renders.

Keeping this in the API means the author edits the real default instead of
discovering the gloss only in the preview, where it can't be reworded.
(customer, 2026-07-31)
"""
from __future__ import annotations

from reportbuilder.api.routes_questions import _scale_gloss
from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable


def _scale_var(name, label, *, wording=("En lainkaan houkuttelevana",
                                        "Erittäin houkuttelevana")):
    lo, hi = wording
    labels = (ValueLabel(1.0, f"1 - {lo}"), ValueLabel(2.0, "2"), ValueLabel(3.0, "3"),
              ValueLabel(4.0, "4"), ValueLabel(5.0, f"5 - {hi}"))
    return Variable(name=name, label=label, measurement="scale",
                    value_labels=labels, missing_values=frozenset())


def _battery(*vars_):
    model = QuestionModel(variables={v.name: v for v in vars_}, questions=[])
    q = Question(qid="b", kind="battery",
                 variables=tuple(v.name for v in vars_), text="Arvioi seuraavia")
    return model, q


def test_battery_gloss_comes_from_the_shared_scale():
    model, q = _battery(_scale_var("s1", "Houkuttelevuus"),
                        _scale_var("s2", "Laadukkuus"))
    assert _scale_gloss(model, q) == (
        "1 = En lainkaan houkuttelevana · 5 = Erittäin houkuttelevana")


def test_merged_battery_gloss_is_the_first_members_wording():
    """Documents WHY the subtitle must stay editable: members merged from separate
    questions keep their own wording, and only the first one's reaches the gloss."""
    model, q = _battery(
        _scale_var("s1", "Houkuttelevuus"),
        _scale_var("s2", "Laadukkuus", wording=("Ei lainkaan laadukas",
                                                "Erittäin laadukas")))
    gloss = _scale_gloss(model, q)
    assert "houkuttelevana" in gloss
    assert "laadukas" not in gloss


def test_single_question_gloss_comes_from_its_value_labels():
    var = _scale_var("s1", "Houkuttelevuus")
    model = QuestionModel(variables={"s1": var}, questions=[])
    q = Question(qid="q1", kind="single", variables=("s1",), text="Kuinka houkuttelevana?")
    assert _scale_gloss(model, q) == (
        "1 = En lainkaan houkuttelevana · 5 = Erittäin houkuttelevana")


def test_no_gloss_for_a_categorical_question():
    var = Variable(name="c1", label="Sukupuoli", measurement="nominal",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies"),
                                 ValueLabel(3.0, "Muu")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"c1": var}, questions=[])
    q = Question(qid="q1", kind="single", variables=("c1",), text="Sukupuoli")
    assert _scale_gloss(model, q) == ""


def test_no_gloss_for_a_multi_question():
    var = Variable(name="m1", label="Vaihtoehto", measurement="nominal",
                   value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"m1": var}, questions=[])
    q = Question(qid="m", kind="multi", variables=("m1",), text="Valitse")
    assert _scale_gloss(model, q) == ""


def test_bare_number_scale_yields_no_gloss():
    """Nothing to move off the legend when the endpoints carry no wording."""
    var = Variable(name="s1", label="Arvio", measurement="scale",
                   value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                   missing_values=frozenset())
    model = QuestionModel(variables={"s1": var}, questions=[])
    q = Question(qid="q1", kind="single", variables=("s1",), text="Arvio")
    assert _scale_gloss(model, q) == ""
