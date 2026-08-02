"""Splitting a rating battery by a classifying variable.

A concept test shows part of the sample packaging 1 and part packaging 2, then
asks the same battery of both — so the battery MUST be splittable by that path.
Both battery paths previously ignored `classifying_var` entirely.

- mean battery  : categories = statements, segments = the classifier's groups.
- stacked battery: three dimensions (statement x level x segment) do not fit a 2-D
  SeriesResult, so the bars become "<statement> · <segment>" combo labels and
  `segment_primary` groups them BY STATEMENT — the two paths sit adjacent, which is
  the comparison a concept test exists to make.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _rating(name, label, n=5):
    return Variable(name=name, label=label, measurement="scale",
                    value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, n + 1)),
                    missing_values=frozenset())


def _setup(rows=200):
    s1 = _rating("s1", "Laadukkuus")
    s2 = _rating("s2", "Modernius")
    clf = Variable(name="polku", label="Polku", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Polku 1"), ValueLabel(2.0, "Polku 2")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"s1": s1, "s2": s2, "polku": clf}, questions=[])
    q = Question(qid="b", kind="battery", variables=("s1", "s2"), text="Battery")
    half = rows // 2
    df = pd.DataFrame({
        # path 1 rates 5, path 2 rates 1 -> unmistakable difference
        "s1": [5.0] * half + [1.0] * half,
        "s2": [4.0] * half + [2.0] * half,
        "polku": [1.0] * half + [2.0] * half,
    })
    return model, q, df


def _spec(chart_type, **kw):
    base = dict(question_ref="b", chart_type=chart_type, statistic="pct",
                classifying_var="polku", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


# ---- mean battery ----------------------------------------------------------
def test_mean_battery_segments_are_the_classifier_groups():
    model, q, df = _setup()
    r = engine.compute(q, _spec("vertical_bar"), df, model)
    assert r.categories == ("Laadukkuus", "Modernius")
    assert set(r.segments) == {"Polku 1", "Polku 2", "Total"}


def test_mean_battery_means_differ_per_segment():
    model, q, df = _setup()
    r = engine.compute(q, _spec("vertical_bar"), df, model)
    assert r.cell("Laadukkuus", "Polku 1").mean == 5.0
    assert r.cell("Laadukkuus", "Polku 2").mean == 1.0
    assert r.cell("Modernius", "Polku 1").mean == 4.0
    assert r.cell("Modernius", "Polku 2").mean == 2.0


def test_mean_battery_bases_are_per_segment():
    model, q, df = _setup()
    r = engine.compute(q, _spec("vertical_bar"), df, model)
    assert r.base_n["Polku 1"] == 100
    assert r.base_n["Polku 2"] == 100


def test_mean_battery_without_a_classifier_is_unchanged():
    model, q, df = _setup()
    r = engine.compute(q, _spec("vertical_bar", classifying_var=None), df, model)
    assert r.segments == ("Total",)
    assert r.cell("Laadukkuus", "Total").mean == 3.0


# ---- stacked battery -------------------------------------------------------
def test_stacked_battery_bars_are_statement_by_segment():
    model, q, df = _setup()
    r = engine.compute(q, _spec("stacked_horizontal_bar"), df, model)
    assert r.categories == ("1", "2", "3", "4", "5")      # the stack is untouched
    assert r.segments == ("Laadukkuus · Polku 1", "Laadukkuus · Polku 2",
                          "Modernius · Polku 1", "Modernius · Polku 2")


def test_stacked_battery_groups_by_statement():
    """segment_primary drives the renderer's grouping — statements adjacent."""
    model, q, df = _setup()
    r = engine.compute(q, _spec("stacked_horizontal_bar"), df, model)
    assert r.segment_primary == {
        "Laadukkuus · Polku 1": "Laadukkuus",
        "Laadukkuus · Polku 2": "Laadukkuus",
        "Modernius · Polku 1": "Modernius",
        "Modernius · Polku 2": "Modernius",
    }


def test_stacked_battery_cells_split_by_segment():
    model, q, df = _setup()
    r = engine.compute(q, _spec("stacked_horizontal_bar"), df, model)
    # path 1 rated Laadukkuus 5 -> 100% at level "5"
    assert r.cell("5", "Laadukkuus · Polku 1").pct == 100.0
    assert r.cell("1", "Laadukkuus · Polku 2").pct == 100.0


def test_stacked_battery_each_bar_sums_to_100():
    model, q, df = _setup()
    r = engine.compute(q, _spec("stacked_horizontal_bar"), df, model)
    for seg in r.segments:
        total = sum((r.cell(c, seg).pct or 0) for c in r.categories)
        assert abs(total - 100.0) < 0.6


def test_stacked_battery_bases_are_per_statement_and_segment():
    model, q, df = _setup()
    r = engine.compute(q, _spec("stacked_horizontal_bar"), df, model)
    assert r.base_n["Laadukkuus · Polku 1"] == 100
    assert r.base_n["Laadukkuus · Polku 2"] == 100


def test_stacked_battery_without_a_classifier_is_unchanged():
    model, q, df = _setup()
    r = engine.compute(q, _spec("stacked_horizontal_bar", classifying_var=None), df, model)
    assert r.segments == ("Laadukkuus", "Modernius")
    assert r.segment_primary is None


def test_stacked_battery_splits_by_a_banner_classifier_too():
    """The banner encoding must work here as well as a value-labelled column."""
    model, q, df = _setup()
    for nm, lbl in (("Polku1", "Polku 1"), ("Polku2", "Polku 2")):
        model.variables[nm] = Variable(name=nm, label=lbl, measurement="categorical",
                                       value_labels=(), missing_values=frozenset())
    model.questions.append(Question(qid="polkubanner", kind="multi",
                                    variables=("Polku1", "Polku2"), text="Polku"))
    df["Polku1"] = [1.0] * 100 + [None] * 100
    df["Polku2"] = [None] * 100 + [1.0] * 100
    r = engine.compute(q, _spec("stacked_horizontal_bar",
                                classifying_var="polkubanner"), df, model)
    assert r.segments == ("Laadukkuus · Polku 1", "Laadukkuus · Polku 2",
                          "Modernius · Polku 1", "Modernius · Polku 2")


def test_a_segment_with_no_answers_is_dropped():
    """Some studies ask each path its OWN variable set (Houkuttelevuus_1 for path 1,
    Houkuttelevuus_2 for path 2). Cross-tabbing one of those batteries by the path
    then leaves the other path empty — drop it rather than draw blank bars.
    Matches _multi, which already skips segments with no rows."""
    model, q, df = _setup()
    # this battery was only asked of path 1
    df.loc[df["polku"] == 2.0, ["s1", "s2"]] = None
    r = engine.compute(q, _spec("stacked_horizontal_bar"), df, model)
    assert r.segments == ("Laadukkuus · Polku 1", "Modernius · Polku 1")
    assert all(r.base_n[s] > 0 for s in r.segments)


def test_mean_battery_drops_an_empty_segment_too():
    model, q, df = _setup()
    df.loc[df["polku"] == 2.0, ["s1", "s2"]] = None
    r = engine.compute(q, _spec("vertical_bar"), df, model)
    assert "Polku 2" not in r.segments
    assert "Polku 1" in r.segments
