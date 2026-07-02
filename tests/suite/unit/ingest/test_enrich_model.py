"""End-to-end tests for ``enrich_model`` — the single grouping entry point.

Covers: it runs without error and returns a QuestionModel on a real read_sav
model; it groups O-pattern/binary multis; it produces battery questions on a
grid model; and multi-response grouping is applied BEFORE battery grouping.
Deterministic (only tmp_path SAV I/O).
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.multi_group import enrich_model, suggest_multi_groups
from reportbuilder.ingest.battery_group import suggest_batteries
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.question import Question, QuestionModel, Variable, ValueLabel
from reportbuilder.testing.fixtures import synthetic_sav


def _var(name, label, *, measurement="scale", codes=None):
    vls = tuple(ValueLabel(float(c), lbl) for c, lbl in (codes or []))
    return Variable(name=name, label=label, measurement=measurement,
                    value_labels=vls, missing_values=frozenset())


def _model(variables):
    qs = [Question(qid=n, kind="single", variables=(n,), text=v.label)
          for n, v in variables.items()]
    return QuestionModel(variables=dict(variables), questions=qs)


# ---- on a real read_sav model ----------------------------------------------

def test_enrich_returns_question_model_on_synthetic(tmp_path):
    _, model = read_sav(synthetic_sav(tmp_path))
    enriched = enrich_model(model)
    assert isinstance(enriched, QuestionModel)


def test_enrich_groups_synthetic_channel_multi(tmp_path):
    # m1/m2 are binary with shared prefix "m" -> one multi.
    _, model = read_sav(synthetic_sav(tmp_path))
    enriched = enrich_model(model)
    multis = [q for q in enriched.questions if q.kind == "multi"]
    assert len(multis) == 1
    assert set(multis[0].variables) == {"m1", "m2"}


def test_enrich_preserves_ungrouped_singles(tmp_path):
    _, model = read_sav(synthetic_sav(tmp_path))
    enriched = enrich_model(model)
    qids = {q.qid for q in enriched.questions}
    assert "q1" in qids and "age" in qids


def test_enrich_keeps_all_variables(tmp_path):
    _, model = read_sav(synthetic_sav(tmp_path))
    enriched = enrich_model(model)
    assert set(enriched.variables) == set(model.variables)


# ---- battery production on a grid model ------------------------------------

def _grid_model(categories, subjects, question="Rate impression of the brand"):
    variables = {}
    idx = 0
    for subj in subjects:
        for cat in categories:
            name = f"g{idx}"
            idx += 1
            variables[name] = _var(name, f"{cat}:{subj}:{question}")
    return _model(variables)


def test_enrich_produces_battery_questions_on_grid():
    m = _grid_model(["Warm", "Trusty", "Modern"], ["Attendo", "Esperi"])
    enriched = enrich_model(m)
    batteries = [q for q in enriched.questions if q.kind == "battery"]
    assert len(batteries) == 2


# ---- ordering: multi applied BEFORE batteries ------------------------------

def test_multi_grouping_applied_before_battery_grouping():
    """Decisive ordering probe: grid cells whose names ALSO follow the O-pattern
    with a shared stem. If multi ran first, the O-pattern consumes all cells into
    one multi, leaving no single questions for the battery pass -> no batteries.
    If batteries ran first, we would instead see battery questions."""
    cats = ["Warm", "Trusty", "Modern"]
    subjects = ["Attendo", "Esperi", "Rinne"]
    variables = {}
    idx = 0
    for subj in subjects:
        for cat in cats:
            idx += 1
            name = f"var7O{idx}"   # shared O-stem var7
            variables[name] = _var(name, f"{cat}:{subj}:Rate impression")
    m = _model(variables)

    # Sanity: on the RAW model both passes would independently fire.
    assert len(suggest_batteries(m)) == 3
    assert len(suggest_multi_groups(m)) == 1

    enriched = enrich_model(m)
    kinds = [q.kind for q in enriched.questions]
    # Multi ran first and ate every cell -> exactly one multi, zero batteries.
    assert kinds == ["multi"]


def test_enrich_groups_keep_deck_position():
    # A model with BOTH an O-pattern multi (distinct stem) and a grid battery.
    # The multi's members come FIRST in the deck, the battery cells after.
    variables = {
        "var9O1": _var("var9O1", "Apple:Which brands here", codes=[(0, "n"), (1, "y")]),
        "var9O2": _var("var9O2", "Pear:Which brands here", codes=[(0, "n"), (1, "y")]),
    }
    idx = 0
    for subj in ["Attendo", "Esperi"]:
        for cat in ["Warm", "Trusty", "Modern"]:
            variables[f"g{idx}"] = _var(f"g{idx}", f"{cat}:{subj}:Rate impression")
            idx += 1
    m = _model(variables)
    enriched = enrich_model(m)
    kinds = [q.kind for q in enriched.questions]
    assert "multi" in kinds and "battery" in kinds
    # Groups sit at their first member's position, so the multi (members first in the
    # deck) precedes the batteries (whose cells come after it).
    assert kinds.index("multi") < kinds.index("battery")
