"""A summary-statistic chart (mean/median/sum) split by two background variables
side by side, instead of crossed. (spec 2026-08-04-separate-classifier-panels, Task 4)"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup():
    q = Variable(name="q", label="Arvosana", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Arvosana")
    # q cycles 1,2,3,4 every 4 rows (80 rows total).
    # sex: first 40 rows Nainen(1.0), last 40 Mies(2.0) -> each sex's rows still
    #   see the full 1,2,3,4 cycle, so both sexes' mean/sum are IDENTICAL to each
    #   other and to the overall total (a deliberate check that segmentation
    #   doesn't accidentally cross with "age" and skew the sex split).
    # age: alternates Nuoret(1.0)/Vanhat(2.0) every row -> Nuoret only ever lands
    #   on q in {1, 3} and Vanhat only ever on q in {2, 4}, giving age groups
    #   DISTINCT means (2.0 vs 3.0) unlike the two (identical) sex groups.
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0] * 20,
        "sex": ([1.0] * 40) + ([2.0] * 40),
        "age": [1.0, 2.0] * 40,
    })
    return model, question, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="mean",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_summary_segments_are_the_sum_not_the_product():
    """2 sex groups + 2 age groups = 4 groups, plus each variable's own "Total"
    reference (show_total defaults to True for a non-pct statistic) = 6 segments —
    never the 2x2=4 CROSSED combos a crossed layout would produce for this data."""
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert list(r.segments) == [
        "Sukupuoli · Nainen", "Sukupuoli · Mies", "Sukupuoli · Total",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Vanhat", "Ikäryhmät · Total",
    ]
    assert r.base_n["Total"] == 80
    assert len(set(r.segment_primary.values())) == 2


def test_segment_primary_maps_every_segment_including_each_panels_total():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.segment_primary["Sukupuoli · Nainen"] == "Sukupuoli"
    assert r.segment_primary["Sukupuoli · Total"] == "Sukupuoli"
    assert r.segment_primary["Ikäryhmät · Vanhat"] == "Ikäryhmät"
    assert r.segment_primary["Ikäryhmät · Total"] == "Ikäryhmät"


def test_bases_are_per_group_and_grand_total_survives():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.base_n["Sukupuoli · Nainen"] == 40
    assert r.base_n["Sukupuoli · Mies"] == 40
    assert r.base_n["Sukupuoli · Total"] == 80
    assert r.base_n["Ikäryhmät · Nuoret"] == 40
    assert r.base_n["Ikäryhmät · Vanhat"] == 40
    assert r.base_n["Ikäryhmät · Total"] == 80
    assert r.base_n["Total"] == 80, "the N footer indexes base_n['Total'] directly"


def test_means_are_computed_from_each_segments_own_mask():
    """The two sex groups see the identical 1..4 cycle (mean 2.5 each, matching the
    80-row grand mean), while the two age groups are DISTINCT from each other and
    from 2.5 — a crossed layout could not produce this pairing (it would instead
    emit 4 thin combo cells, none of which is a clean per-variable mean)."""
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.cell("Arvosana", "Sukupuoli · Nainen").mean == 2.5
    assert r.cell("Arvosana", "Sukupuoli · Mies").mean == 2.5
    assert r.cell("Arvosana", "Sukupuoli · Total").mean == 2.5
    assert r.cell("Arvosana", "Ikäryhmät · Nuoret").mean == 2.0
    assert r.cell("Arvosana", "Ikäryhmät · Vanhat").mean == 3.0
    assert r.cell("Arvosana", "Ikäryhmät · Total").mean == 2.5


def test_non_mean_statistic_uses_the_extra_slot():
    """A "sum" statistic (not "mean") must land in cell.extra, not cell.mean —
    exercising the branch _summary's classifier path already has for non-mean
    stats. Sums also make the per-group distinction obvious: Nuoret totals
    20x1 + 20x3 = 80, Vanhat totals 20x2 + 20x4 = 120."""
    model, question, df = _setup()
    r = engine.compute(question, _spec(statistic="sum"), df, model)
    assert r.cell("Arvosana", "Ikäryhmät · Nuoret").mean is None
    assert r.cell("Arvosana", "Ikäryhmät · Nuoret").value("sum") == 80.0
    assert r.cell("Arvosana", "Ikäryhmät · Vanhat").value("sum") == 120.0
    assert r.cell("Arvosana", "Sukupuoli · Nainen").value("sum") == 100.0
    assert r.cell("Arvosana", "Sukupuoli · Mies").value("sum") == 100.0


def test_crossed_layout_is_untouched():
    """Without xtab_layout=separate, the same two classifiers still CROSS: 2x2 =
    4 combo segments plus "Total" — proving this task didn't change crossed
    behaviour (REQ: separate mode must be opt-in via options.xtab_layout)."""
    model, question, df = _setup()
    r = engine.compute(question, _spec(options={"xtab_layout": "auto"}), df, model)
    assert len([s for s in r.segments if s != "Total"]) == 4, "2 x 2 crossed combos"
    assert not any(" · " in s and s.startswith(("Sukupuoli", "Ikäryhmät"))
                   for s in r.segments), "crossed segments are NOT variable-prefixed"
