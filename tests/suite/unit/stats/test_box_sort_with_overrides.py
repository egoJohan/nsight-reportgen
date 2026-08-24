"""Shortening a category label must not switch the sort off.

The stacked-bar sorts ("order the groups by their top-2 share") match the
scale's top levels against the categories being drawn. The scale levels came
straight off the variable while the categories carry the author's label
overrides, so the moment anyone shortened "Erittäin tyytyväinen" to "Erittäin
tyyt." nothing matched, the sort found no levels to sum, and it silently did
nothing — bars in default order, sort control still showing "Top 2".

Renaming a label for the slide is the most ordinary edit there is.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (ChartSpec, ElementToggles, NumberFormat,
                                        SortSpec)
from reportbuilder.stats import engine

WORDS = ["Erittäin tyytymätön", "Tyytymätön", "Ei kumpaakaan",
         "Tyytyväinen", "Erittäin tyytyväinen"]


def _model():
    v = Variable(name="q", label="Tyytyväisyys", measurement="categorical",
                 value_labels=tuple(ValueLabel(float(i + 1), t)
                                    for i, t in enumerate(WORDS)),
                 missing_values=frozenset())
    seg = Variable(name="g", label="Ryhmä", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Ryhmä A"), ValueLabel(2.0, "Ryhmä B")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": v, "g": seg}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Tyytyväisyys")
    # Ryhmä A: mostly negative. Ryhmä B: mostly positive. A top-2 sort must put
    # B first; the default (data) order has A first.
    a = [1.0] * 40 + [2.0] * 40 + [5.0] * 20
    b = [5.0] * 60 + [4.0] * 30 + [1.0] * 10
    df = pd.DataFrame({"q": a + b, "g": [1.0] * 100 + [2.0] * 100})
    return model, q, df


def _spec(overrides=()):
    return ChartSpec(
        question_ref="q", chart_type="stacked_horizontal_bar", statistic="pct",
        classifying_var="g", number_format=NumberFormat(),
        sort=SortSpec(basis="topbox_sum"), template_slot="s",
        elements=ElementToggles(),
        category_label_overrides=tuple(overrides))


def _bars(spec):
    model, q, df = _model()
    return [s for s in engine.compute(q, spec, df, model).segments if s != "Total"]


def test_the_top_box_sort_puts_the_most_satisfied_group_first():
    assert _bars(_spec()) == ["Ryhmä B", "Ryhmä A"]


def test_it_still_does_when_the_labels_have_been_shortened():
    shortened = [("Erittäin tyytyväinen", "Erittäin tyyt."),
                 ("Tyytyväinen", "Tyyt.")]
    assert _bars(_spec(shortened)) == ["Ryhmä B", "Ryhmä A"]
