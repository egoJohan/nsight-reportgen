"""A categorical variable whose codes carry no labels still makes a chart.

Reported from a live study: "jostain syystä kuvaaja ei generoidu ollenkaan.
N-luku näyttää että data on luettu sisään mutta siitä ei synny mitään" — the
footer said N = 665 and the slide was empty.

The variable is nominal, holds 1 / 2 / 99 (99 declared missing), and its SAV
carries no value labels at all — not lost on the way in; the file has none. The
categories were built from those labels, so there were none, and a chart with no
categories draws the "no data" placeholder over a base computed from data that
is plainly there.

The codes are what the file gives, so the codes are what the chart shows. An
author who wants words puts them in the category-label editor.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _spec(ref="q1", **kw):
    base = dict(question_ref=ref, chart_type="horizontal_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def _model(measurement="categorical", labels=(), missing=(99.0,)):
    var = Variable(name="q1", label="19 Onko käyttöönotto sujunut ilman ongelmia?",
                   measurement=measurement,
                   value_labels=tuple(ValueLabel(*v) for v in labels),
                   missing_values=frozenset(missing))
    return QuestionModel(
        variables={"q1": var},
        questions=[Question(qid="q1", kind="single", variables=("q1",), text=var.label)])


def _df(values):
    return pd.DataFrame({"q1": values})


def test_the_codes_become_the_categories():
    model = _model()
    df = _df([1.0] * 400 + [2.0] * 265 + [99.0] * 23)
    r = engine.compute(model.question("q1"), _spec(), df, model)
    assert r.categories == ("1", "2")
    assert r.base_n["Total"] == 665


def test_the_percentages_are_of_the_base_the_footer_reports():
    """665, not the 688 rows: the 23 respondents coded 99 are declared missing.
    Percentages are rounded for display, so the counts carry the precision."""
    model = _model()
    df = _df([1.0] * 400 + [2.0] * 265 + [99.0] * 23)
    r = engine.compute(model.question("q1"), _spec(), df, model)
    assert r.cell("1", "Total").count == 400
    assert r.cell("2", "Total").count == 265
    assert r.cell("1", "Total").pct == pytest.approx(400 / 665 * 100, abs=0.5)
    assert r.cell("2", "Total").pct == pytest.approx(265 / 665 * 100, abs=0.5)


def test_a_labelled_variable_is_untouched():
    model = _model(labels=((1.0, "Kyllä"), (2.0, "Ei")))
    r = engine.compute(model.question("q1"), _spec(), _df([1.0] * 3 + [2.0]), model)
    assert r.categories == ("Kyllä", "Ei")


def test_a_code_that_is_declared_missing_is_not_a_category():
    model = _model()
    r = engine.compute(model.question("q1"), _spec(), _df([1.0, 2.0, 99.0]), model)
    assert "99" not in r.categories


def test_a_continuous_variable_does_not_become_hundreds_of_categories():
    """Age is not a category list. Nothing to chart is the right answer there —
    the fallback exists for codes, and 40 distinct values are not codes."""
    model = _model(measurement="scale", missing=())
    r = engine.compute(model.question("q1"), _spec(),
                       _df([float(20 + i % 40) for i in range(400)]), model)
    assert r.categories == ()


def test_codes_come_out_in_numeric_order():
    model = _model(missing=())
    r = engine.compute(model.question("q1"), _spec(),
                       _df([3.0, 1.0, 2.0, 10.0, 2.0]), model)
    assert r.categories == ("1", "2", "3", "10")


# ── the same variable used the other way round ───────────────────────────────

def test_it_can_also_be_SPLIT_by():
    """The fallback was wired into the single-question path only, so the very
    variable that now charts fine could not be used as a classifier: the mask
    builder asks for value labels, finds none, and the split silently does not
    happen — no error, just a chart of the whole sample."""
    from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable

    asked = Variable(name="q1", label="Suositteletko?", measurement="categorical",
                     value_labels=(ValueLabel(1.0, "Kyllä"), ValueLabel(2.0, "Ei")),
                     missing_values=frozenset())
    clf = Variable(name="g", label="Ryhmä", measurement="categorical",
                   value_labels=(), missing_values=frozenset())
    model = QuestionModel(
        variables={"q1": asked, "g": clf},
        questions=[Question(qid="q1", kind="single", variables=("q1",), text="Q")])
    df = pd.DataFrame({"q1": [1.0, 2.0] * 10, "g": [1.0] * 10 + [2.0] * 10})
    r = engine.compute(model.question("q1"), _spec(classifying_var="g"), df, model)
    assert set(r.segments) == {"1", "2", "Total"}, r.segments
    assert r.base_n["1"] == 10 and r.base_n["2"] == 10


def test_a_combo_line_is_drawn_for_it_too():
    """A combo maps each drawn category back to the code behind it, through the
    value labels. With none, every lookup missed and the line came out empty —
    bars with nothing over them, and no error to say why."""
    from reportbuilder.model.question import Question, QuestionModel, Variable

    asked = Variable(name="q1", label="Q", measurement="categorical",
                     value_labels=(), missing_values=frozenset())
    score = Variable(name="score", label="Score", measurement="scale",
                     value_labels=(), missing_values=frozenset())
    model = QuestionModel(
        variables={"q1": asked, "score": score},
        questions=[Question(qid="q1", kind="single", variables=("q1",), text="Q")])
    df = pd.DataFrame({"q1": [1.0] * 10 + [2.0] * 10,
                       "score": [3.0] * 10 + [7.0] * 10})
    r = engine.compute(model.question("q1"),
                       _spec(chart_type="combo",
                             options={"combo_secondary": "score"}), df, model)
    line = r.segments[1]
    assert r.cell("1", line).pct == pytest.approx(3.0)
    assert r.cell("2", line).pct == pytest.approx(7.0)
