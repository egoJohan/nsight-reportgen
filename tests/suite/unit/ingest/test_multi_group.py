"""Unit tests for multi-response grouping heuristics and helpers.

Models are built by hand (no SAV) so each behavior is isolated. Deterministic.
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.multi_group import (
    _group_text,
    _is_binary,
    _option_labels,
    _prefix,
    _shared_question,
    apply_groups,
    suggest_multi_groups,
)
from reportbuilder.model.question import Question, QuestionModel, Variable, ValueLabel


# ---- builders --------------------------------------------------------------

def _var(name, label, *, measurement="categorical", codes=None):
    vls = tuple(ValueLabel(float(c), lbl) for c, lbl in (codes or []))
    return Variable(name=name, label=label, measurement=measurement,
                    value_labels=vls, missing_values=frozenset())

BINARY = [(0, "Unchecked"), (1, "Checked")]


def _model(variables):
    qs = [Question(qid=n, kind="single", variables=(n,), text=v.label)
          for n, v in variables.items()]
    return QuestionModel(variables=dict(variables), questions=qs)


# ---- _prefix ---------------------------------------------------------------

def test_prefix_strips_o_pattern_suffix():
    assert _prefix("var10O1") == "var10"
    assert _prefix("var10O2") == "var10"


def test_prefix_strips_trailing_digits():
    assert _prefix("chan3") == "chan"


def test_prefix_leaves_bare_name():
    assert _prefix("abc") == "abc"


# ---- _is_binary ------------------------------------------------------------

def test_is_binary_true_for_zero_one():
    assert _is_binary(_var("m", "m", codes=BINARY)) is True


def test_is_binary_true_for_single_one_code():
    assert _is_binary(_var("m", "m", codes=[(1, "Yes")])) is True


def test_is_binary_true_for_single_zero_code():
    assert _is_binary(_var("m", "m", codes=[(0, "No")])) is True


def test_is_binary_false_when_no_value_labels():
    assert _is_binary(_var("m", "m")) is False


def test_is_binary_false_for_non_binary_codes():
    assert _is_binary(_var("m", "m", codes=[(1, "a"), (2, "b")])) is False


# ---- suggest_multi_groups: O-pattern strategy ------------------------------

def test_o_pattern_groups_members_sharing_stem():
    m = _model({
        "var10O1": _var("var10O1", "Opt A:What brands"),
        "var10O2": _var("var10O2", "Opt B:What brands"),
        "solo": _var("solo", "Solo question"),
    })
    assert suggest_multi_groups(m) == [("var10O1", "var10O2")]


def test_o_pattern_requires_at_least_two_members():
    m = _model({"var10O1": _var("var10O1", "Only one member")})
    assert suggest_multi_groups(m) == []


def test_o_pattern_groups_regardless_of_measurement():
    # Scale/text O-pattern slot families still group (strategy 1 ignores type).
    m = _model({
        "var17O1": _var("var17O1", "slot one", measurement="scale"),
        "var17O2": _var("var17O2", "slot two", measurement="scale"),
    })
    assert suggest_multi_groups(m) == [("var17O1", "var17O2")]


def test_o_pattern_is_case_insensitive_on_the_o():
    m = _model({
        "var5o1": _var("var5o1", "a"),
        "var5o2": _var("var5o2", "b"),
    })
    assert suggest_multi_groups(m) == [("var5o1", "var5o2")]


# ---- suggest_multi_groups: prefix/binary strategy --------------------------

def test_binary_group_by_shared_prefix():
    m = _model({
        "chan1": _var("chan1", "Channel one", codes=BINARY),
        "chan2": _var("chan2", "Channel two", codes=BINARY),
    })
    assert suggest_multi_groups(m) == [("chan1", "chan2")]


def test_binary_not_grouped_when_prefix_differs():
    m = _model({
        "chanA": _var("chanA", "A", codes=BINARY),
        "chanB": _var("chanB", "B", codes=BINARY),
    })
    # Names lack trailing digits: prefix is the whole name -> distinct buckets.
    assert suggest_multi_groups(m) == []


def test_non_binary_scale_without_labels_excluded_from_binary_strategy():
    # A pure numeric scale (no value labels) is not binary -> not grouped.
    m = _model({
        "rate1": _var("rate1", "r1", measurement="scale"),
        "rate2": _var("rate2", "r2", measurement="scale"),
    })
    assert suggest_multi_groups(m) == []


def test_o_pattern_members_excluded_from_binary_strategy():
    # var8O1/var8O2 are binary AND O-pattern: they group once (as one O-group),
    # not twice.
    m = _model({
        "var8O1": _var("var8O1", "a", codes=BINARY),
        "var8O2": _var("var8O2", "b", codes=BINARY),
    })
    assert suggest_multi_groups(m) == [("var8O1", "var8O2")]


def test_o_groups_precede_prefix_groups_in_order():
    m = _model({
        "var3O1": _var("var3O1", "o a"),
        "var3O2": _var("var3O2", "o b"),
        "tick1": _var("tick1", "t a", codes=BINARY),
        "tick2": _var("tick2", "t b", codes=BINARY),
    })
    groups = suggest_multi_groups(m)
    assert groups == [("var3O1", "var3O2"), ("tick1", "tick2")]


# ---- _shared_question ------------------------------------------------------

def test_shared_question_identical_returns_the_text():
    right = "What brands do you know"
    assert _shared_question([right, right]) == right


def test_shared_question_near_identical_returns_longest():
    longest = "What brands are you aware of in the market"
    truncated = "What brands are you aware of in the m"
    assert _shared_question([longest, truncated]) == longest


def test_shared_question_unrelated_returns_none():
    assert _shared_question(["Apple pie recipe here", "Zebra crossing over there"]) is None


def test_shared_question_too_short_returns_none():
    assert _shared_question(["abc", "abc"]) is None


def test_shared_question_empty_returns_none():
    assert _shared_question([]) is None
    assert _shared_question(["", ""]) is None


def test_shared_question_single_item_returns_it():
    assert _shared_question(["one long question here"]) == "one long question here"


def test_shared_question_small_common_fraction_returns_none():
    # Long common prefix (>=20) but < 40% of the longest -> not merged.
    short = "Common prefix here xx"
    long = short + "A" * 100
    assert _shared_question([long, short]) is None


# ---- _option_labels / _group_text ------------------------------------------

def test_group_text_extracts_shared_question_from_option_colon_pattern():
    m = _model({
        "var10O1": _var("var10O1", "Apple:Which brands do you recognize here"),
        "var10O2": _var("var10O2", "Banana:Which brands do you recognize here"),
    })
    assert _group_text(m, ("var10O1", "var10O2")) == "Which brands do you recognize here"


def test_option_labels_maps_member_to_left_side():
    m = _model({
        "var10O1": _var("var10O1", "Apple:Which brands do you recognize here"),
        "var10O2": _var("var10O2", "Banana:Which brands do you recognize here"),
    })
    assert _option_labels(m, ("var10O1", "var10O2")) == {
        "var10O1": "Apple", "var10O2": "Banana",
    }


def test_option_labels_none_when_no_colon():
    m = _model({
        "a1": _var("a1", "Plain label one"),
        "a2": _var("a2", "Plain label two"),
    })
    assert _option_labels(m, ("a1", "a2")) is None


def test_option_labels_none_when_right_sides_unrelated():
    m = _model({
        "var5O1": _var("var5O1", "Apple:Totally different question A here"),
        "var5O2": _var("var5O2", "Banana:Something else entirely B there"),
    })
    assert _option_labels(m, ("var5O1", "var5O2")) is None


def test_group_text_falls_back_to_first_label_when_no_common_prefix():
    m = _model({
        "var5O1": _var("var5O1", "Apple:Totally different question A here"),
        "var5O2": _var("var5O2", "Banana:Something else entirely B there"),
    })
    # No shared right side and no common raw prefix -> first label.
    assert _group_text(m, ("var5O1", "var5O2")) == "Apple:Totally different question A here"


def test_group_text_falls_back_to_common_prefix_stripped():
    m = _model({
        "s1": _var("s1", "Which product - variant one"),
        "s2": _var("s2", "Which product - variant two"),
    })
    # No colon pattern -> common string prefix, stripped of trailing " :-".
    assert _group_text(m, ("s1", "s2")) == "Which product - variant"


# ---- apply_groups ----------------------------------------------------------

@pytest.fixture
def grouped_model():
    m = _model({
        "var10O1": _var("var10O1", "Apple:Which brands do you recognize here"),
        "var10O2": _var("var10O2", "Banana:Which brands do you recognize here"),
        "solo": _var("solo", "A solo question"),
    })
    groups = suggest_multi_groups(m)
    return m, groups, apply_groups(m, groups)


def test_apply_groups_creates_one_multi_question(grouped_model):
    _, _, m2 = grouped_model
    multis = [q for q in m2.questions if q.kind == "multi"]
    assert len(multis) == 1
    assert multis[0].variables == ("var10O1", "var10O2")


def test_apply_groups_multi_qid_is_the_stem(grouped_model):
    _, _, m2 = grouped_model
    assert m2.question("var10").kind == "multi"


def test_apply_groups_multi_text_is_shared_question(grouped_model):
    _, _, m2 = grouped_model
    assert m2.question("var10").text == "Which brands do you recognize here"


def test_apply_groups_preserves_ungrouped_singles(grouped_model):
    _, _, m2 = grouped_model
    solo = [q for q in m2.questions if q.qid == "solo"]
    assert len(solo) == 1 and solo[0].kind == "single"


def test_apply_groups_variable_count_unchanged(grouped_model):
    m, _, m2 = grouped_model
    assert set(m2.variables) == set(m.variables)


def test_apply_groups_rewrites_member_labels_to_options(grouped_model):
    _, _, m2 = grouped_model
    assert m2.variables["var10O1"].label == "Apple"
    assert m2.variables["var10O2"].label == "Banana"


def test_apply_groups_question_count(grouped_model):
    _, _, m2 = grouped_model
    # One multi + one preserved single.
    assert len(m2.questions) == 2
