"""A tick-box is a tick-box whether or not the export named its codes.

Reported from staging: in the Kaiutinboksi study the Manage grouping dialog
offered NOTHING — "muuttujat eivät tule näkyviin listaan". 272 variables, and
269 of them carry no value labels at all: 222 hold only `1.0` (ticked, blank
otherwise) and 19 hold a clean 0/1. They are the reasons-for-purchase
multi-response set — Hyvä tarjous, Myyjän suositus, Läheisen tuttavan
suositus — exported by a platform that wrote no labels.

Both groupability tests read value labels alone, so every one of those was
invisible. The rule is shape, not labels: no labels, and the data holds
nothing but 0/1 with at least one tick. Same principle as the continuous
measures fix. (Johan, 2026-09-11)
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.ingest.multi_group import _is_binary, is_tickbox
from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel

NA = float("nan")


def _var(name, *, codes=(), measurement="categorical", label=None):
    return Variable(name=name, label=label if label is not None else name,
                    measurement=measurement,
                    value_labels=tuple(ValueLabel(float(c), l) for c, l in codes),
                    missing_values=frozenset())


def _df(**cols):
    return pd.DataFrame(cols)


class TestUnlabelled:
    def test_ticked_or_blank_is_a_tickbox(self):
        """222 of the study's variables look exactly like this."""
        v = _var("Hyvatarjous")
        assert is_tickbox(v, _df(Hyvatarjous=[1.0, NA, 1.0, NA]))

    def test_zero_or_one_is_a_tickbox(self):
        v = _var("Akt_IPTV")
        assert is_tickbox(v, _df(Akt_IPTV=[0.0, 1.0, 1.0, 0.0]))

    def test_a_two_point_code_is_not(self):
        """Gender coded 1/2 is a single-choice question, not a tick-box."""
        v = _var("Gender")
        assert not is_tickbox(v, _df(Gender=[1.0, 2.0, 1.0]))

    def test_a_rating_scale_without_labels_is_not(self):
        v = _var("Q23")
        assert not is_tickbox(v, _df(Q23=[1.0, 5.0, 10.0, 7.0]))

    def test_a_continuous_measure_is_not(self):
        v = _var("Age", measurement="scale")
        assert not is_tickbox(v, _df(Age=[41.0, 63.0, 22.0]))

    def test_an_empty_column_is_not(self):
        v = _var("UniqueId")
        assert not is_tickbox(v, _df(UniqueId=[NA, NA, NA]))

    def test_all_zeroes_is_not(self):
        """Nobody ticked it, or it is a dead flag -- either way there is no
        evidence of a tick, and a column of zeroes is not a finding."""
        v = _var("Never")
        assert not is_tickbox(v, _df(Never=[0.0, 0.0, 0.0]))

    def test_a_column_absent_from_the_data_is_not(self):
        assert not is_tickbox(_var("Gone"), _df(Other=[1.0]))

    def test_without_data_it_falls_back_to_the_labels(self):
        """Every caller that has no DataFrame keeps the answer it had."""
        assert not is_tickbox(_var("Hyvatarjous"), None)
        assert is_tickbox(_var("X", codes=[(0, "No"), (1, "Yes")]), None)


class TestLabelledIsUnchanged:
    """The label-based answer wins wherever there are labels -- this must add
    variables to the pool, never take any away or reclassify one."""

    def test_a_labelled_binary_stays_a_tickbox(self):
        v = _var("X", codes=[(0, "Unchecked"), (1, "Checked")])
        assert is_tickbox(v, _df(X=[0.0, 1.0])) and _is_binary(v)

    def test_a_labelled_scale_stays_out(self):
        v = _var("Q", codes=[(1, "Ei lainkaan"), (2, "Vähän"), (3, "Paljon")])
        assert not is_tickbox(v, _df(Q=[1.0, 2.0, 3.0]))

    def test_labels_win_over_data(self):
        """A labelled 1..5 scale whose respondents all answered 1 is still a
        scale -- the labels say what the variable IS."""
        v = _var("Q", codes=[(i, f"p{i}") for i in range(1, 6)])
        assert not is_tickbox(v, _df(Q=[1.0, 1.0, 1.0]))


class TestAutoDetectionIsLeftAlone:
    """Widening AUTO grouping would silently reshape every study already in
    the system -- questions merging on their own, decks changing under people.
    Only the paths an analyst drives are widened: the pool they pick from, and
    the group they explicitly ask for."""

    def test_two_unlabelled_tickboxes_are_not_auto_grouped(self):
        from reportbuilder.ingest.multi_group import suggest_multi_groups
        vars_ = {n: _var(n) for n in ("Syy_Hinta", "Syy_Laatu")}
        qs = [Question(qid=n, kind="single", variables=(n,), text=n) for n in vars_]
        model = QuestionModel(variables=vars_, questions=qs)
        assert suggest_multi_groups(model) == []


class TestTheGroupTheAnalystAsksFor:
    def test_a_manual_multi_of_unlabelled_tickboxes_is_honoured(self):
        """Without this the pool offers them, the analyst groups them, and the
        override drops the group on the floor -- nothing happens and there is
        no message saying why."""
        from reportbuilder.ingest.grouping_override import apply_grouping_override
        vars_ = {n: _var(n) for n in ("Hyvatarjous", "Myyjansuositus")}
        qs = [Question(qid=n, kind="single", variables=(n,), text=n) for n in vars_]
        model = QuestionModel(variables=vars_, questions=qs)
        df = _df(Hyvatarjous=[1.0, NA, 1.0], Myyjansuositus=[NA, 1.0, 1.0])
        override = {"groups": [{"kind": "multi",
                                "variables": ["Hyvatarjous", "Myyjansuositus"]}]}

        out = apply_grouping_override(model, override, df=df)
        assert [q.kind for q in out.questions] == ["multi"]
        assert set(out.questions[0].variables) == {"Hyvatarjous", "Myyjansuositus"}

    def test_without_data_the_group_is_still_skipped_as_before(self):
        """Unchanged behaviour for a caller that has no DataFrame."""
        from reportbuilder.ingest.grouping_override import apply_grouping_override
        vars_ = {n: _var(n) for n in ("Hyvatarjous", "Myyjansuositus")}
        qs = [Question(qid=n, kind="single", variables=(n,), text=n) for n in vars_]
        model = QuestionModel(variables=vars_, questions=qs)
        out = apply_grouping_override(model, {"groups": [
            {"kind": "multi", "variables": ["Hyvatarjous", "Myyjansuositus"]}]})
        assert [q.kind for q in out.questions] == ["single", "single"]
