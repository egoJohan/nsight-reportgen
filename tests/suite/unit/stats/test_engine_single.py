"""Unit tests for engine._single via compute() — single categorical distributions."""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.model.report import (
    ChartSpec, NumberFormat, SortSpec, ElementToggles,
)
from reportbuilder.stats import engine


def _spec(**kw):
    base = dict(question_ref="q", chart_type="vertical_bar", statistic="pct",
                classifying_var=None, number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def _catvar(missing=()):
    return Variable(name="q", label="Q", measurement="categorical",
                    value_labels=(ValueLabel(1.0, "Red"), ValueLabel(2.0, "Green"),
                                  ValueLabel(3.0, "Blue"), ValueLabel(9.0, "NA")),
                    missing_values=frozenset(missing))


def _model_q(var):
    return (QuestionModel(variables={"q": var}, questions=[]),
            Question(qid="q", kind="single", variables=("q",), text="Q"))


def test_single_column_percentages_and_base():
    var = _catvar(missing=(9.0,))
    model, q = _model_q(var)
    df = pd.DataFrame({"q": [1, 1, 2, 2, 2, 3, 9, 9, None]})
    r = engine.compute(q, _spec(), df, model)
    # user-missing (9) and NaN excluded from categories AND base
    assert r.categories == ("Red", "Green", "Blue")
    assert r.base_n == {"Total": 6}
    assert r.cell("Red", "Total").pct == 33.0
    assert r.cell("Green", "Total").pct == 50.0
    assert r.cell("Blue", "Total").pct == 17.0
    assert r.cell("Green", "Total").count == 3.0


def test_single_user_missing_label_not_shown_as_category():
    var = _catvar(missing=(9.0,))
    model, q = _model_q(var)
    df = pd.DataFrame({"q": [1, 2, 3, 9]})
    r = engine.compute(q, _spec(), df, model)
    assert "NA" not in r.categories


def test_rating_scale_reorders_out_of_order_codes():
    # codes stored out of order but labelled "1".."7"
    rvar = Variable(name="r", label="R", measurement="scale",
                    value_labels=(ValueLabel(10.0, "2"), ValueLabel(20.0, "3"),
                                  ValueLabel(30.0, "4"), ValueLabel(40.0, "5"),
                                  ValueLabel(50.0, "6"), ValueLabel(5.0, "1"),
                                  ValueLabel(60.0, "7")),
                    missing_values=frozenset())
    model = QuestionModel(variables={"r": rvar}, questions=[])
    q = Question(qid="r", kind="single", variables=("r",), text="R")
    df = pd.DataFrame({"r": [5.0, 10, 20, 30, 40, 50, 60, 5, 60]})
    r = engine.compute(q, _spec(question_ref="r"), df, model)
    # ordered by scale point parsed from labels, not stored code order
    assert r.categories == ("1", "2", "3", "4", "5", "6", "7")


def test_show_not_answered_appends_bucket_last_and_uses_total_base():
    var = _catvar(missing=(9.0,))
    model, q = _model_q(var)
    df = pd.DataFrame({"q": [1, 1, 2, 2, 2, 3, 9, 9, None]})
    r = engine.compute(q, _spec(show_not_answered=True), df, model)
    assert r.categories[-1] == "Not answered"
    assert r.categories == ("Red", "Green", "Blue", "Not answered")
    # base = total respondents (valid + missing + sysmis)
    assert r.base_n == {"Total": 9}
    # 2 nines + 1 NaN -> 3 not answered
    assert r.cell("Not answered", "Total").count == 3.0
    total_pct = sum(r.cell(c, "Total").pct for c in r.categories)
    assert abs(total_pct - 100.0) <= 2.0


def test_show_empty_categories_false_drops_zero_but_keeps_small_nonzero():
    var = Variable(name="q", label="Q", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Big"), ValueLabel(2.0, "Tiny"),
                                 ValueLabel(3.0, "Zero")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": var}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    df = pd.DataFrame({"q": [1.0] * 997 + [2.0] * 4})  # base 1001; Tiny=0.4%, Zero=0%
    nf = NumberFormat(mode="manual", pct_decimals=1)
    r = engine.compute(q, _spec(show_empty_categories=False, number_format=nf), df, model)
    # 0.0% "Zero" dropped; 0.4% "Tiny" kept
    assert "Zero" not in r.categories
    assert set(r.categories) == {"Big", "Tiny"}
    assert r.cell("Tiny", "Total").pct == 0.4


def test_show_empty_true_keeps_zero_rows():
    var = Variable(name="q", label="Q", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "Big"), ValueLabel(2.0, "Tiny"),
                                 ValueLabel(3.0, "Zero")),
                   missing_values=frozenset())
    model = QuestionModel(variables={"q": var}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    df = pd.DataFrame({"q": [1.0] * 997 + [2.0] * 4})
    r = engine.compute(q, _spec(show_empty_categories=True), df, model)
    assert r.categories == ("Big", "Tiny", "Zero")


def test_not_answered_codes_none_vs_empty_vs_value_changes_effective_missing():
    var = Variable(name="q", label="Q", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B"),
                                 ValueLabel(9.0, "NA")),
                   missing_values=frozenset({9.0}))
    model = QuestionModel(variables={"q": var}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    df = pd.DataFrame({"q": [1, 1, 2, 9, 9]})

    # None -> use var.missing_values ({9}); base excludes the two 9s
    r_none = engine.compute(q, _spec(not_answered_codes=None), df, model)
    assert r_none.base_n["Total"] == 3
    assert r_none.categories == ("A", "B")

    # () -> only NaN is missing; 9 becomes a real category
    r_empty = engine.compute(q, _spec(not_answered_codes=()), df, model)
    assert r_empty.base_n["Total"] == 5
    assert "NA" in r_empty.categories

    # (2,) -> 2 treated as missing, 9 becomes a category
    r_val = engine.compute(q, _spec(not_answered_codes=(2.0,)), df, model)
    assert r_val.base_n["Total"] == 4
    assert "B" not in r_val.categories
    assert "NA" in r_val.categories


def test_label_overrides_change_display_not_order():
    var = _catvar(missing=(9.0,))
    model, q = _model_q(var)
    df = pd.DataFrame({"q": [1, 2, 3]})
    r = engine.compute(q, _spec(category_label_overrides=(("Red", "R!"),)), df, model)
    # display swapped for Red -> "R!" but position (data order) unchanged
    assert r.categories == ("R!", "Green", "Blue")


def test_classifier_produces_segments_plus_total():
    var = Variable(name="q", label="Q", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
                   missing_values=frozenset())
    seg = Variable(name="g", label="g", measurement="categorical",
                   value_labels=(), missing_values=frozenset())
    model = QuestionModel(variables={"q": var, "g": seg}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    df = pd.DataFrame({"q": [1, 1, 2, 2], "g": [1, 2, 1, 2]})
    r = engine.compute(q, _spec(classifying_var="g"), df, model)
    assert r.segments[-1] == "Total"
    assert set(r.segments) == {"1", "2", "Total"}
    assert r.base_n["Total"] == 4


def _model_qg(qvar, gvar):
    return (QuestionModel(variables={"q": qvar, "g": gvar}, questions=[]),
            Question(qid="q", kind="single", variables=("q",), text="Q"))


def test_tiny_base_segment_not_plotted():
    """A classifier value with a near-empty base (e.g. 'En halua sanoa', n=1) must
    not render a misleading 100%. The engine computes it exactly, but the render
    decompose (series_values) drops it."""
    from reportbuilder.render.image._mpl import series_values
    q = _catvar()
    g = Variable(name="g", label="Gender", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "M"), ValueLabel(2.0, "F"),
                               ValueLabel(3.0, "Rare")),
                 missing_values=frozenset())
    model, qq = _model_qg(q, g)
    df = pd.DataFrame({
        "q": ([1, 2, 3, 1] * 5) + ([1, 2, 3, 2] * 5) + [2],  # 41 valid answers
        "g": [1] * 20 + [2] * 20 + [3] * 1,                   # M=20, F=20, Rare=1
    })
    r = engine.compute(qq, _spec(classifying_var="g"), df, model)
    assert "Rare" in r.segments              # engine keeps the exact stat
    _cats, segs, _data = series_values(r)
    assert "Rare" not in segs                # but it is NOT plotted (tiny base)
    assert "M" in segs and "F" in segs


def test_two_classifiers_produce_ordered_cross_product():
    """Two classifiers (gender × age) → cross-product segments, ordered so the
    primary (gender) clusters, with per-combo counts and base_n. Labels join both."""
    q = _catvar()  # Red/Green/Blue (+NA 9)
    g1 = Variable(name="g1", label="Gender", measurement="categorical",
                  value_labels=(ValueLabel(1.0, "M"), ValueLabel(2.0, "F")),
                  missing_values=frozenset())
    g2 = Variable(name="g2", label="Age", measurement="categorical",
                  value_labels=(ValueLabel(1.0, "Young"), ValueLabel(2.0, "Old")),
                  missing_values=frozenset())
    model = QuestionModel(variables={"q": q, "g1": g1, "g2": g2}, questions=[])
    qq = Question(qid="q", kind="single", variables=("q",), text="Q")
    rows_q, rows_g1, rows_g2 = [], [], []
    for (a, b) in [(1, 1), (1, 2), (2, 1), (2, 2)]:      # each combo: 10 rows, 6 Red/4 Green
        for i in range(10):
            rows_q.append(1 if i < 6 else 2)
            rows_g1.append(a)
            rows_g2.append(b)
    df = pd.DataFrame({"q": rows_q, "g1": rows_g1, "g2": rows_g2})
    r = engine.compute(qq, _spec(classifying_var="g1", classifying_var_2="g2"), df, model)
    # Primary (gender) clusters; the Total BAR is dropped for cross-tab.
    assert list(r.segments) == ["M · Young", "M · Old", "F · Young", "F · Old"]
    assert "Total" not in r.segments
    assert r.cell("Red", "M · Young").count == 6.0
    assert r.cell("Green", "F · Old").count == 4.0
    assert r.base_n["M · Young"] == 10
    assert r.base_n["Total"] == 40   # kept for the footer "n = N"
    # Each combo is tagged with its primary group, for grouped rendering.
    assert r.segment_primary == {
        "M · Young": "M", "M · Old": "M", "F · Young": "F", "F · Old": "F"}


def test_endpoint_labelled_scale_shows_all_points_as_numbers_with_caption():
    """A 1-7 scale labelled only on the endpoints must show ALL points (not just the
    two labelled ones) as numbers, 7 at top, with the endpoint text in a caption."""
    v = Variable(name="q", label="Suosittelu", measurement="scale",
                 value_labels=(ValueLabel(1.0, "täysin eri mieltä"),
                               ValueLabel(7.0, "täysin samaa mieltä")),
                 missing_values=frozenset())
    model = QuestionModel(variables={"q": v}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Suosittelu")
    df = pd.DataFrame({"q": [1, 2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 7, 7, 7, 7]})
    r = engine.compute(q, _spec(sort=SortSpec(basis="data_order")), df, model)
    assert r.categories == ("7", "6", "5", "4", "3", "2", "1")   # all points, 7 at top
    assert r.caption is not None
    assert "1 = täysin eri mieltä" in r.caption and "7 = täysin samaa mieltä" in r.caption
    assert r.cell("3", "Total").count == 3.0
    assert r.cell("7", "Total").count == 4.0


def test_endpoint_scale_shows_full_range_including_empty_points():
    """A scale point with ZERO responses still shows (as 0%) so the 1-7 scale has no
    gaps — the categories are the full contiguous range, not just data-present points."""
    v = Variable(name="q", label="Q", measurement="scale",
                 value_labels=(ValueLabel(1.0, "täysin eri"), ValueLabel(7.0, "täysin samaa")),
                 missing_values=frozenset())
    model = QuestionModel(variables={"q": v}, questions=[])
    q = Question(qid="q", kind="single", variables=("q",), text="Q")
    df = pd.DataFrame({"q": [1, 2, 3, 5, 6, 7, 7, 7]})   # NO 4s
    r = engine.compute(q, _spec(sort=SortSpec(basis="data_order")), df, model)
    assert r.categories == ("7", "6", "5", "4", "3", "2", "1")  # 4 present, no gap
    assert r.cell("4", "Total").count == 0.0
    assert r.cell("4", "Total").pct == 0.0
