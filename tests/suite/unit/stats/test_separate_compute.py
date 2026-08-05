"""compute() must not relabel separate-mode segments, and the banner guard must
only fire for CROSSED layouts."""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup_banner():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    p1 = Variable(name="p1", label="Polku 1", measurement="categorical",
                  value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                  missing_values=frozenset())
    p2 = Variable(name="p2", label="Polku 2", measurement="categorical",
                  value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                  missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Vanhat")),
                   missing_values=frozenset())
    polku = Question(qid="polku", kind="multi", variables=("p1", "p2"), text="Polku")
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    model = QuestionModel(variables={"q": q, "p1": p1, "p2": p2, "age": age},
                          questions=[polku, question])
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0] * 20,
        "p1": ([1.0] * 40) + ([0.0] * 40),
        "p2": ([0.0] * 40) + ([1.0] * 40),
        "age": [1.0, 2.0] * 40,
    })
    return model, question, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="polku", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(), options={})
    base.update(kw)
    return ChartSpec(**base)


def test_banner_crossed_with_a_second_variable_still_raises():
    model, question, df = _setup_banner()
    with pytest.raises(ValueError, match="banner"):
        engine.compute(question, _spec(options={"xtab_layout": "auto"}), df, model)


def test_banner_is_allowed_in_separate_mode():
    model, question, df = _setup_banner()
    r = engine.compute(question, _spec(options={"xtab_layout": "separate"}), df, model)
    assert list(r.segments) == [
        "Polku · Polku 1", "Polku · Polku 2",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Vanhat",
    ]


def test_separate_labels_survive_compute_untouched():
    model, question, df = _setup_banner()
    r = engine.compute(question, _spec(options={"xtab_layout": "separate"}), df, model)
    assert all(" · " in s for s in r.segments)
    assert not any("|" in s for s in r.segments), "no combo relabelling ran"


def _setup_comparison():
    """A COMPARISON question (two multi questions overlaid as series) with a stale
    banner `classifying_var` + a `classifying_var_2` still sitting in the spec.

    `_multi_comparison` / `_battery_comparison` never consult a classifier — the
    series ARE the member questions — so this has always computed fine, ignoring
    both. (2026-08-04 final review, I5)"""
    def _yn(name, label):
        return Variable(name=name, label=label, measurement="categorical",
                        value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                        missing_values=frozenset())

    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Vanhat")),
                   missing_values=frozenset())
    polku = Question(qid="polku", kind="multi", variables=("p1", "p2"), text="Polku")
    qa = Question(qid="qa", kind="multi", variables=("a1", "a2"), text="Kysymys A")
    qb = Question(qid="qb", kind="multi", variables=("b1", "b2"), text="Kysymys B")
    cmp_q = Question(qid="cmp", kind="comparison", variables=(), text="Vertailu",
                     members=("qa", "qb"))
    model = QuestionModel(
        variables={"p1": _yn("p1", "Polku 1"), "p2": _yn("p2", "Polku 2"),
                   "a1": _yn("a1", "A1"), "a2": _yn("a2", "A2"),
                   "b1": _yn("b1", "B1"), "b2": _yn("b2", "B2"), "age": age},
        questions=[polku, qa, qb, cmp_q])
    df = pd.DataFrame({
        "p1": ([1.0] * 40) + ([0.0] * 40),
        "p2": ([0.0] * 40) + ([1.0] * 40),
        "a1": [1.0, 0.0] * 40, "a2": [0.0, 1.0] * 40,
        "b1": [1.0, 1.0, 0.0, 0.0] * 20, "b2": [0.0, 0.0, 1.0, 1.0] * 20,
        "age": [1.0, 2.0] * 40,
    })
    return model, cmp_q, df


def test_a_comparison_slide_ignores_a_leftover_banner_and_second_classifier():
    """REGRESSION: relocating the banner guard out of `_banner_masks` put it ABOVE
    the `kind == "comparison"` dispatch, so a saved "compare questions" slide
    carrying a banner primary + any second classifier started raising — 422 on
    preview, blank on export — even though the comparison paths read neither.
    (2026-08-04 final review, I5)"""
    model, cmp_q, df = _setup_comparison()
    spec = ChartSpec(question_ref="cmp", chart_type="horizontal_bar", statistic="pct",
                     classifying_var="polku", classifying_var_2="age",
                     number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                     template_slot="s", elements=ElementToggles(), options={})
    r = engine.compute(cmp_q, spec, df, model)
    # The series are the two MEMBER questions (labelled by their distinguishing
    # part), not the banner's members and not any age group — both classifiers
    # were ignored, exactly as before the guard moved.
    assert len(r.segments) == 2
    assert not any(x in s for s in r.segments
                   for x in ("Polku", "Nuoret", "Vanhat"))


def test_the_banner_guard_still_fires_for_a_non_comparison_question():
    """The relocation must not weaken the guard for the kinds that DO read the
    classifiers — the crossed single-question case still raises."""
    model, question, df = _setup_banner()
    with pytest.raises(ValueError, match="banner"):
        engine.compute(question, _spec(), df, model)
