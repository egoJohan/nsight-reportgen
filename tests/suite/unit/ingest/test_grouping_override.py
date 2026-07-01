"""apply_grouping_override — manual grouping wins over auto-detection.

Rule: manual groups applied; forced singles stay single; auto-detection fills the
gaps. Operates on the RAW read_sav model (before enrich).
"""
from __future__ import annotations

from reportbuilder.ingest.grouping_override import apply_grouping_override
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.testing.fixtures import synthetic_sav


def _raw(tmp_path):
    _df, model = read_sav(synthetic_sav(tmp_path))
    return model


def _q(model, qid):
    return next((q for q in model.questions if q.qid == qid), None)


def test_empty_override_equals_enrich(tmp_path):
    raw = _raw(tmp_path)
    got = apply_grouping_override(raw, {})
    exp = enrich_model(raw)
    assert {q.qid: q.kind for q in got.questions} == {q.qid: q.kind for q in exp.questions}


def test_split_forces_members_back_to_single(tmp_path):
    # Auto-detection groups m1+m2 into a multi "m"; forcing them single splits it.
    raw = _raw(tmp_path)
    assert _q(enrich_model(raw), "m").kind == "multi"  # sanity: auto groups it

    got = apply_grouping_override(raw, {"groups": [], "singles": ["m1", "m2"]})
    assert _q(got, "m") is None, "the auto 'm' multi must be dissolved"
    assert _q(got, "m1").kind == "single"
    assert _q(got, "m2").kind == "single"


def test_manual_group_with_label(tmp_path):
    raw = _raw(tmp_path)
    got = apply_grouping_override(
        raw,
        {"groups": [{"kind": "multi", "variables": ["m1", "m2"], "label": "My brands"}],
         "singles": []},
    )
    multis = [q for q in got.questions if q.kind == "multi"]
    assert len(multis) == 1
    assert tuple(multis[0].variables) == ("m1", "m2")
    assert multis[0].text == "My brands"


def test_forced_single_not_regrouped_by_auto(tmp_path):
    # Forcing just one member dissolves the auto O/prefix group for that family.
    raw = _raw(tmp_path)
    got = apply_grouping_override(raw, {"groups": [], "singles": ["m1"]})
    assert _q(got, "m") is None
    assert _q(got, "m1").kind == "single"


def test_battery_kind_is_skipped_not_error(tmp_path):
    raw = _raw(tmp_path)
    got = apply_grouping_override(
        raw, {"groups": [{"kind": "battery", "variables": ["m1", "m2"]}], "singles": []}
    )
    # Phase 1 ignores battery kind — no crash; m1/m2 fall through to auto/single.
    assert all(q.kind != "battery" for q in got.questions)


def test_stale_unknown_variable_is_skipped(tmp_path):
    raw = _raw(tmp_path)
    got = apply_grouping_override(
        raw, {"groups": [{"kind": "multi", "variables": ["m1", "ghost"]}], "singles": []}
    )
    # A group referencing a removed variable is skipped, not fatal.
    assert all("ghost" not in q.variables for q in got.questions)


def test_manual_group_of_arbitrary_singles(tmp_path):
    # Combine two variables that auto-detection would NOT group on its own.
    raw = _raw(tmp_path)
    got = apply_grouping_override(
        raw, {"groups": [{"kind": "multi", "variables": ["q1", "m1"]}], "singles": []}
    )
    m = [q for q in got.questions if q.kind == "multi" and set(q.variables) == {"q1", "m1"}]
    assert len(m) == 1
