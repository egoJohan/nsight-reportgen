"""One slide, part of the classifying variable.

A battery crossed with a classifier is three dimensions — statement x scale
level x group — and a SeriesResult holds two, so every statement becomes
several bars called "<statement> · <group>". Twenty statements by three
countries is sixty bars, and the slide says nothing at all.

What a packaging study actually wants is the whole battery seen through ONE
path: design 1 on this slide, design 2 on the next. So the slide carries the
groups it is computed on. It is a property of the SLIDE, not of the variable —
the same variable is used on both slides; duplicating the slide and changing
the tick is what makes the pair.

Empty means every group, which is what every existing slide has.
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


def _setup(rows=300):
    s1 = _rating("s1", "Laadukkuus")
    s2 = _rating("s2", "Modernius")
    clf = Variable(name="polku", label="Polku", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Design 1"), ValueLabel(2.0, "Design 2"),
                                 ValueLabel(3.0, "Design 3")),
                   missing_values=frozenset())
    single = Variable(name="q1", label="Suositteletko?", measurement="categorical",
                      value_labels=(ValueLabel(1.0, "Kyllä"), ValueLabel(2.0, "Ei")),
                      missing_values=frozenset())
    model = QuestionModel(variables={"s1": s1, "s2": s2, "polku": clf, "q1": single},
                          questions=[])
    battery = Question(qid="b", kind="battery", variables=("s1", "s2"), text="Battery")
    plain = Question(qid="q1", kind="single", variables=("q1",), text="Suositteletko?")
    third = rows // 3
    df = pd.DataFrame({
        "s1": [5.0] * third + [1.0] * third + [3.0] * third,
        "s2": [4.0] * third + [2.0] * third + [3.0] * third,
        "q1": [1.0] * third + [2.0] * third + [1.0] * third,
        "polku": [1.0] * third + [2.0] * third + [3.0] * third,
    })
    return model, battery, plain, df


def _spec(chart_type, ref="b", **kw):
    base = dict(question_ref=ref, chart_type=chart_type, statistic="pct",
                classifying_var="polku", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


# ── the slide is computed on the groups it names ─────────────────────────────

def test_no_selection_is_every_group_exactly_as_before():
    """The field is new; no slide that exists may change because of it."""
    model, battery, _plain, df = _setup()
    before = engine.compute(battery, _spec("vertical_bar"), df, model)
    after = engine.compute(battery, _spec("vertical_bar", classifying_values=()), df, model)
    assert before.segments == after.segments
    assert before.base_n == after.base_n


def test_one_group_leaves_the_battery_one_bar_per_statement():
    """The point of the whole feature: design 1's battery, readable."""
    model, battery, _plain, df = _setup()
    r = engine.compute(battery, _spec("stacked_horizontal_bar",
                                      classifying_values=("Design 1",)), df, model)
    # bars are the statements themselves — no "· Design 1" hung off every one
    assert set(r.segments) == {"Laadukkuus", "Modernius"}


def test_the_selected_group_is_the_only_one_measured():
    """Design 1 rated s1=5 throughout, so its distribution is entirely at 5."""
    model, battery, _plain, df = _setup()
    r = engine.compute(battery, _spec("stacked_horizontal_bar",
                                      classifying_values=("Design 1",)), df, model)
    assert r.cell("5", "Laadukkuus").pct == 100.0
    assert r.cell("1", "Laadukkuus").pct == 0.0


def test_total_is_the_selected_respondents():
    """The slide is a study of the people it selected: one base, and N says so."""
    model, _battery, plain, df = _setup()
    r = engine.compute(plain, _spec("horizontal_bar", ref="q1",
                                    classifying_values=("Design 1",)), df, model)
    assert r.base_n["Total"] == 100
    assert set(r.segments) == {"Design 1", "Total"}


def test_two_groups_keep_both_and_drop_the_third():
    model, _battery, plain, df = _setup()
    r = engine.compute(plain, _spec("horizontal_bar", ref="q1",
                                    classifying_values=("Design 1", "Design 3")), df, model)
    assert set(r.segments) == {"Design 1", "Design 3", "Total"}
    assert r.base_n["Total"] == 200


def test_a_group_that_no_longer_exists_does_not_blank_the_slide():
    """The data can change under a saved slide. A stale grouping already degrades
    rather than 422s here; a stale filter does the same."""
    model, _battery, plain, df = _setup()
    r = engine.compute(plain, _spec("horizontal_bar", ref="q1",
                                    classifying_values=("Design 9",)), df, model)
    assert r.base_n["Total"] == 300
