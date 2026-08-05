"""A single question split by two background variables SIDE BY SIDE."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import QuestionModel, Question, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup():
    q = Variable(name="q", label="Suhtautuminen", measurement="scale",
                 value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
                 missing_values=frozenset())
    sex = Variable(name="sex", label="Sukupuoli", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
                   missing_values=frozenset())
    age = Variable(name="age", label="Ikäryhmät", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Nuoret"), ValueLabel(2.0, "Keski"),
                                 ValueLabel(3.0, "Vanhat")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "sex": sex, "age": age}, questions=[])
    question = Question(qid="q", kind="single", variables=("q",), text="Suhtautuminen")
    df = pd.DataFrame({
        "q": [1.0, 2.0, 3.0, 4.0, 5.0] * 24,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, question, df


def _spec(**kw) -> ChartSpec:
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="sex", classifying_var_2="age",
                number_format=NumberFormat(), sort=SortSpec(basis="data_order"),
                template_slot="s", elements=ElementToggles(),
                options={"xtab_layout": "separate"})
    base.update(kw)
    return ChartSpec(**base)


def test_segments_are_the_sum_of_both_variables_groups():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert list(r.segments) == [
        "Sukupuoli · Nainen", "Sukupuoli · Mies",
        "Ikäryhmät · Nuoret", "Ikäryhmät · Keski", "Ikäryhmät · Vanhat",
    ]


def test_segment_primary_is_the_source_variable():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.segment_primary["Sukupuoli · Nainen"] == "Sukupuoli"
    assert r.segment_primary["Ikäryhmät · Vanhat"] == "Ikäryhmät"
    assert len(set(r.segment_primary.values())) == 2, "one panel per VARIABLE"


def test_bases_are_per_group_and_total_survives():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    assert r.base_n["Sukupuoli · Nainen"] == 60
    assert r.base_n["Ikäryhmät · Nuoret"] == 40
    assert r.base_n["Total"] == 120, "the N footer indexes base_n['Total'] directly"


def test_each_group_sums_to_100_percent():
    model, question, df = _setup()
    r = engine.compute(question, _spec(), df, model)
    for seg in r.segments:
        total = sum((r.cell(c, seg).pct or 0.0) for c in r.categories)
        assert abs(total - 100.0) < 1.5, f"{seg} should be a full distribution"


def test_percent_base_is_forced_to_the_classifier_direction():
    model, question, df = _setup()
    r = engine.compute(question, _spec(percent_base="question"), df, model)
    for seg in r.segments:
        total = sum((r.cell(c, seg).pct or 0.0) for c in r.categories)
        assert abs(total - 100.0) < 1.5


def test_crossed_layout_is_untouched():
    model, question, df = _setup()
    r = engine.compute(question, _spec(options={"xtab_layout": "auto"}), df, model)
    assert len([s for s in r.segments if s != "Total"]) == 6, "2 x 3 combos"


def _setup_uneven():
    """Same variables as `_setup`, but `q`'s OVERALL distribution is uneven — so a
    "pct" sort over the union-of-both-classifiers Total has an unambiguous order.
    (regression for the row-building loop's total_cell, which used to be a hard-coded
    empty Cell in separate mode — see FINDING 1, 2026-08-04 review)"""
    model, question, _ = _setup()
    df = pd.DataFrame({
        "q": [5.0] * 50 + [4.0] * 30 + [3.0] * 20 + [2.0] * 15 + [1.0] * 5,
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, question, df


def test_sort_basis_pct_orders_categories_by_overall_percentage():
    """A separate-mode chart with sort basis "pct" (the UI's default, per
    config_schema.sort_field) must not raise, and must order categories by their
    overall (union-of-both-classifiers) percentage. (FINDING 1, 2026-08-04 review)"""
    model, question, df = _setup_uneven()
    r = engine.compute(question, _spec(sort=SortSpec(basis="pct")), df, model)
    assert list(r.categories) == ["5", "4", "3", "2", "1"]


def _nwc_table(row_sums: list[int], col_sums: list[int]) -> list[list[int]]:
    """Northwest-corner transportation table: a rows x cols matrix whose row/col
    sums match the given targets (feasible because sum(row_sums) == sum(col_sums))."""
    rows, cols = list(row_sums), list(col_sums)
    table = [[0] * len(cols) for _ in range(len(rows))]
    i = j = 0
    while i < len(rows) and j < len(cols):
        v = min(rows[i], cols[j])
        table[i][j] = v
        rows[i] -= v
        cols[j] -= v
        if rows[i] == 0:
            i += 1
        elif cols[j] == 0:
            j += 1
        else:
            break
    return table


def _setup_topbox_panels():
    """A stacked-bar fixture where each panel's groups have DISTINCT top-2 (levels 4
    & 5) shares, so a "topbox_sum" reorder actually moves them, and each panel also
    carries its own "<label> · Total" (resolve_show_total is unconditionally True for
    stacked chart types). Per-code sex/age marginals are built with a transportation
    table so both classifiers' marginals are simultaneously exact. (FINDING 2,
    2026-08-04 review)"""
    model, question, _ = _setup()
    # code -> (Nainen, Mies) / (Nuoret, Keski, Vanhat) counts. Mies and Vanhat lead;
    # each code's two splits sum to the same total (20/20/20/30/30).
    sex_by_code = {1.0: (15, 5), 2.0: (15, 5), 3.0: (12, 8), 4.0: (9, 21), 5.0: (9, 21)}
    age_by_code = {1.0: (12, 6, 2), 2.0: (12, 6, 2), 3.0: (8, 8, 4),
                   4.0: (5, 10, 15), 5.0: (3, 10, 17)}
    sex_codes = (1.0, 2.0)
    age_codes = (1.0, 2.0, 3.0)
    rows = []
    for code in (1.0, 2.0, 3.0, 4.0, 5.0):
        table = _nwc_table(list(sex_by_code[code]), list(age_by_code[code]))
        for si, sex_code in enumerate(sex_codes):
            for ai, age_code in enumerate(age_codes):
                rows.extend([(code, sex_code, age_code)] * table[si][ai])
    df = pd.DataFrame(rows, columns=["q", "sex", "age"])
    return model, question, df


def test_topbox_sort_pins_each_panels_total_at_the_end_of_that_panel():
    model, question, df = _setup_topbox_panels()
    spec = _spec(chart_type="stacked_horizontal_bar",
                 sort=SortSpec(basis="topbox_sum", descending=True))
    r = engine.compute(question, spec, df, model)
    assert list(r.segments) == [
        "Sukupuoli · Mies", "Sukupuoli · Nainen", "Sukupuoli · Total",
        "Ikäryhmät · Vanhat", "Ikäryhmät · Keski", "Ikäryhmät · Nuoret",
        "Ikäryhmät · Total",
    ]


def _setup_half_missing():
    """`q` is MISSING for every "Mies" respondent, so a "Not answered" row has a
    real, per-segment signal to report: 100 % in the Mies group, 0 % in Nainen,
    and 50 % in each age group (which straddle both sexes evenly).

    Breaks the intersection every other separate-mode fixture shares — they all
    run with `show_not_answered` off and no missing data at all, which is exactly
    what hid the mis-keyed missing counts. (2026-08-04 final review, C2)"""
    model, question, _ = _setup()
    df = pd.DataFrame({
        "q": ([1.0, 2.0, 3.0, 4.0, 5.0] * 12) + ([float("nan")] * 60),
        "sex": ([1.0] * 60) + ([2.0] * 60),
        "age": [1.0, 2.0, 3.0] * 40,
    })
    return model, question, df


def test_not_answered_is_counted_per_separate_segment():
    """Pre-fix every segment printed 0.0 %: `_missing_counts` was keyed off the
    primary classifier's RAW CODES ("1", "2") while the segments are named
    "Sukupuoli · Nainen", so every lookup missed. (2026-08-04 final review, C2)"""
    model, question, df = _setup_half_missing()
    r = engine.compute(question, _spec(show_not_answered=True), df, model)
    na = "Not answered"
    assert na in r.categories
    assert r.cell(na, "Sukupuoli · Mies").pct == 100.0
    assert r.cell(na, "Sukupuoli · Nainen").pct == 0.0
    for grp in ("Nuoret", "Keski", "Vanhat"):
        assert r.cell(na, f"Ikäryhmät · {grp}").pct == 50.0


def test_not_answered_footer_n_matches_the_crossed_layout():
    """`base_n["Total"]` is the slide's N footer and is present even though
    "Total" is not a SEGMENT in separate mode. Pre-fix it fell back to the
    valid-only base (60) while the crossed version of the same slide printed 120.
    (2026-08-04 final review, C2 + M8)"""
    model, question, df = _setup_half_missing()
    sep = engine.compute(question, _spec(show_not_answered=True), df, model)
    crossed = engine.compute(
        question, _spec(show_not_answered=True, options={"xtab_layout": "auto"}),
        df, model)
    assert "Total" not in sep.segments, "a bare Total belongs to no panel"
    assert sep.base_n["Total"] == 120
    assert sep.base_n["Total"] == crossed.base_n["Total"]


def test_segment_bases_include_the_not_answered_rows():
    """Each segment's own base grows by its missing rows too, exactly as it does
    in the crossed layout — "Mies" is 60 (all not-answered), not 0."""
    model, question, df = _setup_half_missing()
    r = engine.compute(question, _spec(show_not_answered=True), df, model)
    assert r.base_n["Sukupuoli · Mies"] == 60
    assert r.base_n["Sukupuoli · Nainen"] == 60
    assert r.base_n["Ikäryhmät · Nuoret"] == 40
