"""Unit tests for battery (rating-grid) grouping and helpers.

Grid models built by hand: variables labelled ``"<category>:<subject>:<question>"``.
Deterministic.
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.battery_group import (
    _battery_text,
    _cells,
    apply_batteries,
    suggest_batteries,
)
from reportbuilder.model.question import Question, QuestionModel, Variable


def _var(name, label, *, measurement="scale"):
    return Variable(name=name, label=label, measurement=measurement,
                    value_labels=(), missing_values=frozenset())


def _grid_model(categories, subjects, question="Rate impression of the brand", extra=None):
    """A category x subject grid, plus optional extra (name -> label) singles."""
    variables = {}
    questions = []
    idx = 0
    for subj in subjects:
        for cat in categories:
            name = f"v{idx}"
            idx += 1
            variables[name] = _var(name, f"{cat}:{subj}:{question}")
            questions.append(Question(qid=name, kind="single", variables=(name,),
                                      text=variables[name].label))
    for name, label in (extra or {}).items():
        variables[name] = _var(name, label, measurement="categorical")
        questions.append(Question(qid=name, kind="single", variables=(name,), text=label))
    return QuestionModel(variables=variables, questions=questions)


CATS3 = ["Warm", "Trusty", "Modern"]
SUBJ2 = ["Attendo", "Esperi"]


# ---- _cells ----------------------------------------------------------------

def test_cells_extracts_category_subject_var_stem():
    m = _grid_model(["Warm"], ["Attendo"])
    cells = _cells(m)
    assert cells == [("Warm", "Attendo", "v0", "Rate impression of the brand")]


def test_cells_ignores_labels_without_two_colons():
    m = _grid_model([], [], extra={"plain": "Just a plain question"})
    assert _cells(m) == []


def test_cells_only_looks_at_single_questions():
    m = _grid_model(CATS3, SUBJ2)
    # Everything is single here; 3 cats x 2 subj = 6 cells.
    assert len(_cells(m)) == 6


def test_cells_joins_extra_colons_into_stem():
    m = QuestionModel(
        variables={"v": _var("v", "Cat:Subj:Question: with colon")},
        questions=[Question(qid="v", kind="single", variables=("v",), text="x")],
    )
    assert _cells(m) == [("Cat", "Subj", "v", "Question: with colon")]


# ---- suggest_batteries -----------------------------------------------------

def test_suggest_batteries_one_per_subject():
    m = _grid_model(CATS3, SUBJ2)
    bats = suggest_batteries(m)
    subjects = [s for s, _ in bats]
    assert subjects == ["Attendo", "Esperi"]


def test_suggest_batteries_members_are_categories():
    m = _grid_model(CATS3, SUBJ2)
    bats = suggest_batteries(m)
    _, members = bats[0]
    assert [cat for cat, _var, _stem in members] == CATS3


def test_suggest_batteries_below_min_subjects_returns_none():
    m = _grid_model(CATS3, ["Attendo"])   # only 1 subject
    assert suggest_batteries(m) == []


def test_suggest_batteries_below_min_members_returns_none():
    m = _grid_model(["Warm", "Trusty"], SUBJ2)  # 2 members < default 3
    assert suggest_batteries(m) == []


def test_suggest_batteries_respects_custom_thresholds():
    m = _grid_model(CATS3, SUBJ2)
    assert suggest_batteries(m, min_subjects=3) == []
    assert suggest_batteries(m, min_members=4) == []


def test_suggest_batteries_no_grid_returns_none():
    m = _grid_model([], [], extra={"q1": "Satisfaction", "q2": "Loyalty"})
    assert suggest_batteries(m) == []


# ---- _battery_text ---------------------------------------------------------

def test_battery_text_combines_subject_and_common_theme():
    assert _battery_text("Attendo", ["Rate impression"] * 3) == "Attendo — Rate impression"


def test_battery_text_subject_only_when_no_common_theme():
    assert _battery_text("Attendo", ["Alpha", "Beta"]) == "Attendo"


def test_battery_text_trims_long_theme_at_word_boundary():
    theme = "word " * 40  # >90 chars
    stems = [theme, theme]
    out = _battery_text("S", stems)
    assert out.startswith("S — ")
    assert len(out.split(" — ", 1)[1]) <= 90


# ---- apply_batteries -------------------------------------------------------

@pytest.fixture
def applied():
    m = _grid_model(CATS3, SUBJ2, extra={"plain": "A plain unrelated question"})
    bats = suggest_batteries(m)
    return m, bats, apply_batteries(m, bats)


def test_apply_batteries_creates_battery_questions(applied):
    _, _, m2 = applied
    batteries = [q for q in m2.questions if q.kind == "battery"]
    assert len(batteries) == 2
    assert all(q.kind == "battery" for q in batteries)


def test_apply_batteries_prepends_batteries_before_kept(applied):
    _, _, m2 = applied
    assert m2.questions[0].kind == "battery"
    assert m2.questions[-1].qid == "plain"


def test_apply_batteries_relabels_members_to_category(applied):
    _, _, m2 = applied
    # First subject's first cell was labelled "Warm:Attendo:..." -> now "Warm".
    assert m2.variables["v0"].label == "Warm"


def test_apply_batteries_removes_consumed_singles(applied):
    _, _, m2 = applied
    qids = {q.qid for q in m2.questions}
    assert "v0" not in qids
    assert "plain" in qids


def test_apply_batteries_battery_qid_slug(applied):
    _, _, m2 = applied
    qids = [q.qid for q in m2.questions if q.kind == "battery"]
    assert qids == ["battery-attendo", "battery-esperi"]


def test_apply_batteries_disambiguates_colliding_qids():
    # "Brand X" and "Brand-X" both slug to "brand-x".
    m = _grid_model(CATS3, ["Brand X", "Brand-X"])
    m2 = apply_batteries(m, suggest_batteries(m))
    qids = [q.qid for q in m2.questions if q.kind == "battery"]
    assert qids == ["battery-brand-x", "battery-brand-x-2"]


def test_apply_batteries_empty_returns_model_unchanged():
    m = _grid_model(CATS3, SUBJ2)
    assert apply_batteries(m, []) is m
