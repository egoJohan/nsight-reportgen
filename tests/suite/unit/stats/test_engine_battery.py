"""Unit tests for engine battery paths (_battery and _battery_stacked)."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.stats import engine


def _spec(**kw):
    base = dict(question_ref="b", chart_type="vertical_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def _rating_var(name, label, n=5):
    return Variable(name=name, label=label, measurement="scale",
                    value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, n + 1)),
                    missing_values=frozenset())


def _battery_model():
    s1 = _rating_var("s1", "Statement A")
    s2 = _rating_var("s2", "Statement B")
    model = QuestionModel(variables={"s1": s1, "s2": s2}, questions=[])
    q = Question(qid="b", kind="battery", variables=("s1", "s2"), text="Battery")
    df = pd.DataFrame({"s1": [1, 2, 3, 4, 5], "s2": [5, 5, 4, 4, 3]})
    return model, q, df


def test_battery_mean_per_member():
    model, q, df = _battery_model()
    r = engine.compute(q, _spec(chart_type="vertical_bar"), df, model)
    assert r.statistic == "mean"
    assert r.categories == ("Statement A", "Statement B")
    assert r.cell("Statement A", "Total").mean == 3.0
    assert r.cell("Statement B", "Total").mean == 4.2
    # count carries the answered N per statement
    assert r.cell("Statement A", "Total").count == 5.0
    assert r.base_n == {"Total": 5}


def test_battery_stacked_categories_are_scale_levels():
    model, q, df = _battery_model()
    r = engine.compute(q, _spec(chart_type="stacked_horizontal_bar"), df, model)
    assert r.statistic == "pct"
    # categories = scale levels 1..5
    assert r.categories == ("1", "2", "3", "4", "5")
    # segments = the statements (bars)
    assert r.segments == ("Statement A", "Statement B")


def test_battery_stacked_each_statement_pcts_sum_to_100():
    model, q, df = _battery_model()
    r = engine.compute(q, _spec(chart_type="stacked_horizontal_bar"), df, model)
    for seg in r.segments:
        total = sum(r.cell(cat, seg).pct for cat in r.categories)
        assert abs(total - 100.0) <= 1.0


def test_battery_stacked_cell_counts_match_data():
    model, q, df = _battery_model()
    r = engine.compute(q, _spec(chart_type="stacked_horizontal_bar"), df, model)
    # Statement A has exactly one response at each level 1..5
    for lvl in ("1", "2", "3", "4", "5"):
        assert r.cell(lvl, "Statement A").count == 1.0
    # Statement B: two at 5, two at 4, one at 3
    assert r.cell("5", "Statement B").count == 2.0
    assert r.cell("4", "Statement B").count == 2.0
    assert r.cell("3", "Statement B").count == 1.0


def test_battery_stacked_base_includes_total_and_per_statement():
    model, q, df = _battery_model()
    r = engine.compute(q, _spec(chart_type="stacked_horizontal_bar"), df, model)
    assert r.base_n["Total"] == 5
    assert r.base_n["Statement A"] == 5
    assert r.base_n["Statement B"] == 5


def test_battery_stacked_topbox_sum_orders_statements_by_top2():
    """'Top 2 sum' orders the statement bars by their summed two highest scale levels
    (4+5), descending — the most-'agree' statement leads."""
    model, q, df = _battery_model()  # s1 top2=40%, s2 top2=80%
    r = engine.compute(
        q, _spec(chart_type="stacked_horizontal_bar",
                 sort=SortSpec(basis="topbox_sum", descending=True)), df, model)
    assert r.segments == ("Statement B", "Statement A")
    # default (data_order) keeps variable order
    r2 = engine.compute(q, _spec(chart_type="stacked_horizontal_bar"), df, model)
    assert r2.segments == ("Statement A", "Statement B")


def _word_rating_var(name, label):
    return Variable(name=name, label=label, measurement="scale",
                    value_labels=(ValueLabel(1.0, "Ei lainkaan tärkeä"),
                                  ValueLabel(2.0, "Vähän tärkeä"),
                                  ValueLabel(3.0, "Melko tärkeä"),
                                  ValueLabel(4.0, "Tärkeä"),
                                  ValueLabel(5.0, "Erittäin tärkeä")),
                    missing_values=frozenset())


def test_battery_stacked_word_labelled_scale_renders_levels():
    """A word-labelled scale (no leading digits) now builds the stack via scale_levels."""
    s1 = _word_rating_var("s1", "Statement A")
    s2 = _word_rating_var("s2", "Statement B")
    model = QuestionModel(variables={"s1": s1, "s2": s2}, questions=[])
    q = Question(qid="b", kind="battery", variables=("s1", "s2"), text="Battery")
    df = pd.DataFrame({"s1": [1, 2, 3, 4, 5], "s2": [5, 5, 4, 4, 3]})
    r = engine.compute(q, _spec(chart_type="stacked_horizontal_bar"), df, model)
    assert r.categories == ("Ei lainkaan tärkeä", "Vähän tärkeä", "Melko tärkeä",
                            "Tärkeä", "Erittäin tärkeä")
    assert r.segments == ("Statement A", "Statement B")


def test_battery_comparison_explicit_members():
    def rv(n, l):
        return Variable(name=n, label=l, measurement="scale",
                        value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                        missing_values=frozenset())
    vars_ = {"a1": rv("a1", "Nopeus"), "a2": rv("a2", "Laatu"),
             "b1": rv("b1", "Nopeus"), "b2": rv("b2", "Laatu")}
    qa = Question(qid="qa", kind="battery", variables=("a1", "a2"), text="Attendo — Arvio")
    qb = Question(qid="qb", kind="battery", variables=("b1", "b2"), text="Esperi — Arvio")
    model = QuestionModel(variables=vars_, questions=[qa, qb])
    df = pd.DataFrame({"a1": [5, 4], "a2": [3, 3], "b1": [2, 2], "b2": [4, 4]})
    r = engine._battery_comparison(qa, _spec(chart_type="radar"), df, model, members=[qa, qb])
    assert r.categories == ("Nopeus", "Laatu")
    assert set(r.segments) == {"Attendo", "Esperi"}


# ── Category-label overrides on the battery paths ────────────────────────────
# The label editor lists a battery's MEMBER labels, so a shortened label must reach
# the bars. Regression: the battery paths read `v.label` raw and silently dropped
# every override (customer: merged several questions into one battery, shortened the
# labels, nothing changed in the chart).

_OVERRIDES = (("Statement A", "A"), ("Statement B", "B"))


def test_battery_mean_applies_category_label_overrides():
    model, q, df = _battery_model()
    r = engine.compute(
        q, _spec(chart_type="vertical_bar", category_label_overrides=_OVERRIDES), df, model)
    assert r.categories == ("A", "B")
    assert r.cell("A", "Total").mean == 3.0
    assert r.cell("B", "Total").mean == 4.2


def test_battery_stacked_applies_category_label_overrides():
    model, q, df = _battery_model()
    r = engine.compute(
        q, _spec(chart_type="stacked_horizontal_bar",
                 category_label_overrides=_OVERRIDES), df, model)
    assert r.segments == ("A", "B")
    # the stack itself is untouched — overrides rename the BARS, not the scale levels
    assert r.categories == ("1", "2", "3", "4", "5")
    # cells and per-bar bases follow the display label
    assert r.cell("5", "B").count == 2.0
    assert r.base_n["A"] == 5 and r.base_n["B"] == 5


def test_battery_stacked_overrides_survive_topbox_sort():
    """Sorting the bars by top-2 sum must reorder the DISPLAY labels, not fall back
    to the raw member labels."""
    model, q, df = _battery_model()
    r = engine.compute(
        q, _spec(chart_type="stacked_horizontal_bar",
                 category_label_overrides=_OVERRIDES,
                 sort=SortSpec(basis="topbox_sum", descending=True)), df, model)
    assert r.segments == ("B", "A")


def test_battery_partial_overrides_leave_others_intact():
    model, q, df = _battery_model()
    r = engine.compute(
        q, _spec(chart_type="vertical_bar",
                 category_label_overrides=(("Statement B", "B"),)), df, model)
    assert r.categories == ("Statement A", "B")


def test_battery_comparison_applies_category_label_overrides():
    def rv(n, l):
        return Variable(name=n, label=l, measurement="scale",
                        value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                        missing_values=frozenset())
    vars_ = {"a1": rv("a1", "Nopeus"), "a2": rv("a2", "Laatu"),
             "b1": rv("b1", "Nopeus"), "b2": rv("b2", "Laatu")}
    qa = Question(qid="qa", kind="battery", variables=("a1", "a2"), text="Attendo — Arvio")
    qb = Question(qid="qb", kind="battery", variables=("b1", "b2"), text="Esperi — Arvio")
    model = QuestionModel(variables=vars_, questions=[qa, qb])
    df = pd.DataFrame({"a1": [5, 4], "a2": [3, 3], "b1": [2, 2], "b2": [4, 4]})
    spec = _spec(chart_type="radar", category_label_overrides=(("Nopeus", "Nop."),))
    r = engine._battery_comparison(qa, spec, df, model, members=[qa, qb])
    assert r.categories == ("Nop.", "Laatu")
    # the renamed attribute still resolves per entity (no empty cells)
    assert r.cell("Nop.", "Attendo").mean == 4.5
    assert r.cell("Nop.", "Esperi").mean == 2.0
