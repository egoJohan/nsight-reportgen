"""A pie split by groups can show the whole study as a panel of its own.

Asked for from the field (2026-09-19): "Voiko pie ja doughnut kaavioihin lisätä
mahdollisuuden totaalin näyttämiselle … niin voi olla esim. se ja jokin näistä
ikäryhmistä vierekkäin?" — the Total beside one age group.

Ticking groups narrows the SLIDE to those respondents, so a Total computed on
the narrowed rows is the ticked groups themselves: beside one group it would
repeat that group under another name. The Total panel is the whole study.
"""
from __future__ import annotations

import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.panels import MAX_PANELS, panel_segments
from reportbuilder.stats import engine

pytestmark = pytest.mark.unit


def _setup():
    region = Variable(name="q1", label="Missä asut?", measurement="categorical",
                      value_labels=(ValueLabel(1.0, "Etelä"), ValueLabel(2.0, "Pohjoinen")),
                      missing_values=frozenset())
    age = Variable(name="ika", label="Ikä", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "18–34"), ValueLabel(2.0, "35–54"),
                                 ValueLabel(3.0, "55+"), ValueLabel(4.0, "75+")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q1": region, "ika": age}, questions=[])
    q = Question(qid="q1", kind="single", variables=("q1",), text="Missä asut?")
    # 18–34: all south (100); 35–54: all north (100); 55+: half and half (100);
    # 75+: all south (40).
    df = pd.DataFrame({
        "q1": [1.0] * 100 + [2.0] * 100 + [1.0] * 50 + [2.0] * 50 + [1.0] * 40,
        "ika": [1.0] * 100 + [2.0] * 100 + [3.0] * 100 + [4.0] * 40,
    })
    return model, q, df


def _spec(chart_type="pie", **kw):
    base = dict(question_ref="q1", chart_type=chart_type, statistic="pct",
                classifying_var="ika", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def test_the_total_beside_one_group_is_the_whole_study():
    model, q, df = _setup()
    series = engine.compute(q, _spec(classifying_values=("18–34",), show_total="on"), df, model)

    assert panel_segments(series).labels == ("Total", "18–34")
    assert series.base_n["Total"] == 340, "the Total is everyone, not the ticked group"
    assert series.cell("Etelä", "18–34").pct == pytest.approx(100.0)
    assert series.cell("Etelä", "Total").pct == pytest.approx(190 / 340 * 100, abs=0.5)


def test_a_ticked_groups_numbers_do_not_change_when_the_total_is_added():
    model, q, df = _setup()
    without = engine.compute(q, _spec(classifying_values=("55+",)), df, model)
    with_total = engine.compute(q, _spec(classifying_values=("55+",), show_total="on"), df, model)
    assert with_total.cell("Etelä", "55+").pct == without.cell("Etelä", "55+").pct
    assert with_total.base_n["55+"] == without.base_n["55+"]


def test_unticked_groups_stay_off_the_slide():
    model, q, df = _setup()
    series = engine.compute(q, _spec(classifying_values=("18–34", "55+"), show_total="on"),
                            df, model)
    assert set(series.segments) == {"Total", "18–34", "55+"}


def test_the_total_takes_one_of_the_three_places():
    model, q, df = _setup()
    series = engine.compute(q, _spec(show_total="on"), df, model)
    sel = panel_segments(series)
    assert len(sel.labels) == MAX_PANELS
    assert sel.labels[0] == "Total"
    assert len(sel.capped) == 2, "four groups and a Total: two groups give way"


def test_a_saved_pie_gains_no_panel():
    """`auto` is what every existing slide holds; a Total panel is added only
    when asked for, even where a bar chart's Total would show."""
    model, q, df = _setup()
    for statistic in ("pct", "count"):
        series = engine.compute(q, _spec(classifying_values=("18–34", "35–54"),
                                         statistic=statistic), df, model)
        assert "Total" not in panel_segments(series).labels


@pytest.mark.parametrize("chart_type", ["doughnut", "funnel"])
def test_every_panel_chart_offers_it(chart_type):
    model, q, df = _setup()
    series = engine.compute(q, _spec(chart_type, classifying_values=("35–54",),
                                     show_total="on"), df, model)
    assert panel_segments(series).labels == ("Total", "35–54")
    assert series.base_n["Total"] == 340


def test_a_bar_charts_total_still_counts_the_ticked_groups():
    """Unchanged elsewhere: on a bar chart the Total is a reference series over
    the slide's own respondents, one base for everything on the slide."""
    model, q, df = _setup()
    series = engine.compute(q, _spec("vertical_bar", classifying_values=("18–34",),
                                     show_total="on"), df, model)
    assert series.base_n["Total"] == 100
