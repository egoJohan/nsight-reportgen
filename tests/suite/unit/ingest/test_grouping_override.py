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


def test_non_tickbox_group_is_skipped(tmp_path):
    # q1 is single-choice (Yes/No coded 1/2), not a 0/1 tick-box → the group is
    # ignored (multi-response only makes sense for tick-box variables).
    raw = _raw(tmp_path)
    got = apply_grouping_override(
        raw, {"groups": [{"kind": "multi", "variables": ["q1", "m1"]}], "singles": []}
    )
    assert not any(q.kind == "multi" and "q1" in q.variables for q in got.questions)
    assert _q(got, "q1").kind == "single"


from reportbuilder.model.question import Variable, ValueLabel, Question, QuestionModel


def _scalevar(name, label, n=5):
    return Variable(name=name, label=label, measurement="scale",
                    value_labels=tuple(ValueLabel(float(i), l) for i, l in
                                       zip(range(1, n + 1),
                                           ["Ei lainkaan", "Vähän", "Keski", "Paljon",
                                            "Erittäin", "F", "G"][:n])),
                    missing_values=frozenset())


def _two_scale_model():
    s1, s2 = _scalevar("s1", "Stmt A"), _scalevar("s2", "Stmt B")
    return QuestionModel(variables={"s1": s1, "s2": s2},
                         questions=[Question(qid="s1", kind="single", variables=("s1",), text="Stmt A"),
                                    Question(qid="s2", kind="single", variables=("s2",), text="Stmt B")])


def test_manual_battery_group_creates_battery():
    got = apply_grouping_override(
        _two_scale_model(),
        {"groups": [{"kind": "battery", "variables": ["s1", "s2"], "label": "Importance"}],
         "singles": []})
    bats = [q for q in got.questions if q.kind == "battery"]
    assert len(bats) == 1
    assert set(bats[0].variables) == {"s1", "s2"} and bats[0].text == "Importance"
    assert not any(q.kind == "single" for q in got.questions)  # members absorbed


def test_manual_battery_skipped_when_scales_differ():
    model = QuestionModel(
        variables={"s1": _scalevar("s1", "A", 5), "s2": _scalevar("s2", "B", 3)},
        questions=[Question(qid="s1", kind="single", variables=("s1",), text="A"),
                   Question(qid="s2", kind="single", variables=("s2",), text="B")])
    got = apply_grouping_override(
        model, {"groups": [{"kind": "battery", "variables": ["s1", "s2"], "label": "X"}]})
    assert not any(q.kind == "battery" for q in got.questions)  # mismatched scales → skipped


def test_manual_battery_uses_shared_stem_and_short_qid():
    """A manual battery of 'Subject:Question' scale vars is named by the SHARED
    question (not the labels concatenated), with a short qid; members relabelled."""
    stem = ("Mikä on yleinen käsityksesi tuntemistasi hoivapalveluita tarjoavista "
            "yksityisistä yrityksistä ja toisaalta julkisista palveluista?")
    labs = tuple(ValueLabel(float(i), l) for i, l in
                 zip(range(1, 6), ["Ei", "Vähän", "Keski", "Paljon", "Erittäin"]))
    s1 = Variable(name="s1", label=f"Yksityiset palveluntarjoajat:{stem}",
                  measurement="scale", value_labels=labs, missing_values=frozenset())
    s2 = Variable(name="s2", label=f"Julkinen palveluntarjoaja:{stem}",
                  measurement="scale", value_labels=labs, missing_values=frozenset())
    model = QuestionModel(
        variables={"s1": s1, "s2": s2},
        questions=[Question(qid="s1", kind="single", variables=("s1",), text=s1.label),
                   Question(qid="s2", kind="single", variables=("s2",), text=s2.label)])
    got = apply_grouping_override(
        model, {"groups": [{"kind": "battery", "variables": ["s1", "s2"], "label": ""}]})
    bat = next(q for q in got.questions if q.kind == "battery")
    assert bat.text == stem                          # shared stem, not concatenation
    assert bat.qid.startswith("battery-") and len(bat.qid) <= 60   # short, stable
    assert got.variables["s1"].label == "Yksityiset palveluntarjoajat"   # subject
    assert got.variables["s2"].label == "Julkinen palveluntarjoaja"
