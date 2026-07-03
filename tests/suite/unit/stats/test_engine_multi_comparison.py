"""Parallel-question comparison — overlay several parallel MULTI-response questions
(adjectives) as radar/grouped-bar series sharing the option axes (services).
See docs/superpowers/specs/2026-07-03-parallel-question-comparison-design.md."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import ChartSpec, NumberFormat, SortSpec, ElementToggles
from reportbuilder.stats import engine


def _spec(**kw):
    base = dict(question_ref="rohkea", chart_type="radar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def _tick(name, label):
    return Variable(name=name, label=label, measurement="categorical",
                    value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                    missing_values=frozenset())


def _multi_model():
    """Two adjective multis sharing the option set {IS, IL, HS}."""
    vars_ = {
        "r_is": _tick("r_is", "IS"), "r_il": _tick("r_il", "IL"), "r_hs": _tick("r_hs", "HS"),
        "l_is": _tick("l_is", "IS"), "l_il": _tick("l_il", "IL"), "l_hs": _tick("l_hs", "HS"),
    }
    q_rohkea = Question(qid="rohkea", kind="multi", variables=("r_is", "r_il", "r_hs"),
                        text="Mikä palvelu sopii ominaisuuteen -Rohkea")
    q_luot = Question(qid="luot", kind="multi", variables=("l_is", "l_il", "l_hs"),
                      text="Mikä palvelu sopii ominaisuuteen -Luotettava")
    model = QuestionModel(variables=vars_, questions=[q_rohkea, q_luot])
    df = pd.DataFrame({
        "r_is": [1, 1, 1, 0], "r_il": [1, 0, 0, 0], "r_hs": [0, 0, 1, 1],
        "l_is": [1, 1, 0, 0], "l_il": [1, 1, 1, 0], "l_hs": [0, 0, 0, 1],
    })
    return model, q_rohkea, q_luot, df


def test_parallel_questions_matches_multis_by_option_set():
    model, q_rohkea, q_luot, _ = _multi_model()
    sibs = engine._parallel_questions(q_rohkea, model)
    assert {q.qid for q in sibs} == {"rohkea", "luot"}


def test_parallel_questions_excludes_different_option_set():
    model, q_rohkea, _, _ = _multi_model()
    # A multi with a DIFFERENT option set must not be matched.
    odd = Question(qid="odd", kind="multi", variables=("r_is", "r_il"),
                   text="Eri optiot -X")
    model.questions.append(odd)
    sibs = engine._parallel_questions(q_rohkea, model)
    assert "odd" not in {q.qid for q in sibs}


def test_series_label_tail_adjective():
    _, q_rohkea, q_luot, _ = _multi_model()
    assert engine._series_label(q_rohkea, [q_rohkea, q_luot]) == "Rohkea"
    assert engine._series_label(q_luot, [q_rohkea, q_luot]) == "Luotettava"


def test_series_label_head_entity():
    a = Question(qid="a", kind="battery", variables=(), text="Attendo — Arvioi palvelua")
    b = Question(qid="b", kind="battery", variables=(), text="Esperi — Arvioi palvelua")
    assert engine._series_label(a, [a, b]) == "Attendo"
    assert engine._series_label(b, [a, b]) == "Esperi"


def test_multi_comparison_grid_shape():
    model, q_rohkea, _, df = _multi_model()
    r = engine.compute(q_rohkea, _spec(chart_type="radar"), df, model)
    # categories = the shared options (axes), in this question's order
    assert r.categories == ("IS", "IL", "HS")
    # segments = one polygon per adjective
    assert set(r.segments) == {"Rohkea", "Luotettava"}
    assert r.statistic == "pct"


def test_multi_comparison_cell_pct():
    model, q_rohkea, _, df = _multi_model()
    r = engine.compute(q_rohkea, _spec(chart_type="radar"), df, model)
    # base(Rohkea) = 4 respondents (all have >=1 tick); IS ticked by 3 -> 75%
    assert r.cell("IS", "Rohkea").pct == 75.0
    # base(Luotettava) = 3 (rows 0,1,3 have >=1 tick... row2 has l_il=1 too) -> IL ticked 3x
    assert r.cell("IL", "Luotettava").pct == 75.0


def test_lone_multi_radar_is_single_series():
    """A multi with no parallel siblings renders as ONE polygon (unchanged)."""
    model, q_rohkea, _, df = _multi_model()
    # Drop the sibling so only Rohkea remains parallel-to-itself.
    model.questions.remove(next(q for q in model.questions if q.qid == "luot"))
    r = engine.compute(q_rohkea, _spec(chart_type="radar"), df, model)
    assert r.segments == ("Total",)
    assert r.categories == ("IS", "IL", "HS")


def test_question_carries_comparison_members():
    q = Question(qid="compare-x", kind="comparison", variables=("a", "b"),
                 text="X", members=("adj1", "adj2"))
    assert q.members == ("adj1", "adj2")
    assert Question(qid="q", kind="single", variables=("a",), text="Q").members == ()


def test_multi_comparison_explicit_members_subset():
    model, q_rohkea, q_luot, df = _multi_model()
    r = engine._multi_comparison(q_rohkea, _spec(chart_type="radar"), df, model,
                                 members=[q_rohkea])
    assert set(r.segments) == {"Rohkea"}
    assert r.categories == ("IS", "IL", "HS")
