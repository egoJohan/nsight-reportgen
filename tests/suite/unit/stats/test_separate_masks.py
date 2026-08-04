"""Mask segmentation for the SEPARATE two-variable layout.

Two background variables shown side by side are NOT crossed: each variable
contributes its own groups as ordinary cuts of the sample, so a respondent counts
once in the gender panel and once in the age panel — never in a product of the
two. (spec 2026-08-04-separate-classifier-panels)
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Identifioitko itsesi…?", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Naiseksi"), ValueLabel(2.0, "Mieheksi")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "18-34-vuotiaat"),
                                 ValueLabel(2.0, "35-54-vuotiaat"),
                                 ValueLabel(3.0, "55-69-vuotiaat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_separate_layout_needs_the_option_and_both_variables():
    assert engine._separate_layout(_spec()) is True
    assert engine._separate_layout(_spec(options={"xtab_layout": "auto"})) is False
    assert engine._separate_layout(_spec(options={})) is False
    assert engine._separate_layout(_spec(classifying_var_2=None)) is False


def test_masks_are_the_sum_of_both_variables_groups_not_the_product():
    model, df = _setup()
    masks, _primary = engine._separate_masks(_spec(), df, model)
    assert list(masks) == [
        "Identifioitko itsesi…? · Naiseksi",
        "Identifioitko itsesi…? · Mieheksi",
        "Ikäryhmät · 18-34-vuotiaat",
        "Ikäryhmät · 35-54-vuotiaat",
        "Ikäryhmät · 55-69-vuotiaat",
    ]  # 2 + 3, never 2 x 3


def test_each_mask_is_that_groups_own_rows():
    model, df = _setup()
    masks, _primary = engine._separate_masks(_spec(), df, model)
    assert int(masks["Identifioitko itsesi…? · Naiseksi"].sum()) == 60
    assert int(masks["Ikäryhmät · 18-34-vuotiaat"].sum()) == 40


def test_primary_maps_every_segment_to_its_source_variable():
    model, df = _setup()
    masks, primary = engine._separate_masks(_spec(), df, model)
    assert set(primary) == set(masks)
    assert primary["Identifioitko itsesi…? · Naiseksi"] == "Identifioitko itsesi…?"
    assert primary["Ikäryhmät · 55-69-vuotiaat"] == "Ikäryhmät"


def test_show_total_on_adds_one_total_mask_per_variable():
    model, df = _setup()
    masks, primary = engine._separate_masks(_spec(show_total="on"), df, model)
    assert "Identifioitko itsesi…? · Total" in masks
    assert "Ikäryhmät · Total" in masks
    assert "Total" not in masks, "no bare Total segment — it is not a panel"
    assert primary["Ikäryhmät · Total"] == "Ikäryhmät"
    assert int(masks["Ikäryhmät · Total"].sum()) == 120


def test_show_total_off_adds_none():
    model, df = _setup()
    masks, _primary = engine._separate_masks(_spec(show_total="off"), df, model)
    assert not [s for s in masks if s.endswith(" · Total")]


def test_two_variables_sharing_a_group_label_stay_distinct():
    model, df = _setup()
    model.variables["age"] = Variable(
        name="age", label="Ikäryhmät", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Naiseksi"),) + model.variables["age"].value_labels[1:],
        missing_values=frozenset())
    masks, _primary = engine._separate_masks(_spec(), df, model)
    assert "Identifioitko itsesi…? · Naiseksi" in masks
    assert "Ikäryhmät · Naiseksi" in masks


def test_returns_none_when_not_separate():
    model, df = _setup()
    assert engine._separate_masks(_spec(options={"xtab_layout": "auto"}), df, model) is None
