"""Cross-tabbing by a banner (indicator-column) classifier. (spec 2026-08-02 §2.4)

`classifying_var` carries the QID of a near-partition multi question; resolution is
variable-name-first, so a real column always wins.
"""
from __future__ import annotations

import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.stats import engine


def _setup(n=200):
    half = n // 2
    q = Variable(name="q", label="Q", measurement="categorical",
                 value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
                 missing_values=frozenset())
    p1 = Variable(name="Polku1", label="Polku 1", measurement="categorical",
                  value_labels=(), missing_values=frozenset())
    p2 = Variable(name="Polku2", label="Polku 2", measurement="categorical",
                  value_labels=(), missing_values=frozenset())
    banner = Question(qid="polku", kind="multi", variables=("Polku1", "Polku2"),
                      text="Polku")
    model = QuestionModel(variables={"q": q, "Polku1": p1, "Polku2": p2},
                          questions=[banner])
    df = pd.DataFrame({
        "q": [1.0, 2.0] * (n // 2),
        "Polku1": [1.0] * half + [None] * (n - half),
        "Polku2": [None] * half + [1.0] * (n - half),
    })
    return model, Question(qid="q", kind="single", variables=("q",), text="Q"), df


def _spec(**kw):
    base = dict(question_ref="q", chart_type="horizontal_bar", statistic="pct",
                classifying_var="polku", number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"), template_slot="s",
                elements=ElementToggles())
    base.update(kw)
    return ChartSpec(**base)


def test_segments_are_the_member_labels():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert set(r.segments) == {"Polku 1", "Polku 2", "Total"}


def test_per_segment_bases():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert r.base_n["Polku 1"] == 100
    assert r.base_n["Polku 2"] == 100
    assert r.base_n["Total"] == 200


def test_segment_labels_are_not_mangled_by_the_relabeller():
    """_relabel_segments expects a variable name; handed a qid it must no-op."""
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert "Polku 1" in r.segments


def test_cells_split_by_the_banner_segment():
    model, q, df = _setup()
    r = engine.compute(q, _spec(), df, model)
    assert r.cell("Yes", "Polku 1").count == 50.0
    assert r.cell("No", "Polku 2").count == 50.0


def test_a_non_partition_multi_is_not_used_as_a_classifier():
    """An overlapping tick-box multi must fall through, not become segments."""
    model, q, df = _setup()
    df["Polku2"] = 1.0                       # everyone in both -> 100% overlap
    r = engine.compute(q, _spec(), df, model)
    assert set(r.segments) == {"Total"}


def test_a_real_variable_name_wins_over_a_qid():
    """Resolution order: a DataFrame column always takes precedence."""
    model, q, df = _setup()
    clf = Variable(name="clf", label="C", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
                   missing_values=frozenset())
    model.variables["clf"] = clf
    df["clf"] = [1.0, 2.0] * 100
    r = engine.compute(q, _spec(classifying_var="clf"), df, model)
    assert set(r.segments) == {"A", "B", "Total"}


def test_screened_banner_total_excludes_unqualified_respondents():
    """Only 60% saw a concept; the Total must sit on those 120, not on 200."""
    model, q, df = _setup()
    df.loc[120:, "Polku1"] = None
    df.loc[120:, "Polku2"] = None
    r = engine.compute(q, _spec(), df, model)
    assert r.base_n["Total"] == 120
    for seg in ("Polku 1", "Polku 2"):
        total = sum((r.cell(c, seg).pct or 0) for c in r.categories)
        assert abs(total - 100.0) < 0.5


# ---- unsupported combinations (spec §2.4, §2.5) ----------------------------
import pytest  # noqa: E402


def _with_gender(model, df):
    model.variables["gender"] = Variable(
        name="gender", label="Sukupuoli", measurement="categorical",
        value_labels=(ValueLabel(1.0, "Nainen"), ValueLabel(2.0, "Mies")),
        missing_values=frozenset())
    df["gender"] = [1.0, 2.0] * (len(df) // 2)
    return model, df


def test_second_classifier_with_a_banner_raises_a_clear_error():
    """Crossing overlapping masks with a second variable has no obvious base
    semantics, so it is deferred — but it must SAY so. It used to silently ignore
    the second classifier and return the banner split as if nothing were wrong."""
    model, q, df = _setup()
    model, df = _with_gender(model, df)
    with pytest.raises(ValueError, match="second classifying variable"):
        engine.compute(q, _spec(classifying_var_2="gender"), df, model)


def test_two_ordinary_classifiers_still_cross_tab():
    """The guard must not touch the existing two-classifier cross-tab."""
    model, q, df = _setup()
    model, df = _with_gender(model, df)
    clf = Variable(name="clf", label="C", measurement="categorical",
                   value_labels=(ValueLabel(1.0, "A"), ValueLabel(2.0, "B")),
                   missing_values=frozenset())
    model.variables["clf"] = clf
    df["clf"] = [1.0] * 100 + [2.0] * 100
    r = engine.compute(q, _spec(classifying_var="clf", classifying_var_2="gender"),
                       df, model)
    assert any("·" in s for s in r.segments)


def test_percent_base_question_falls_back_for_a_banner():
    """Overlapping segments cannot be distributed within a category, so the
    'each category' direction must fall back rather than produce nonsense."""
    model, q, df = _setup()
    r = engine.compute(q, _spec(percent_base="question"), df, model)
    for seg in ("Polku 1", "Polku 2"):
        total = sum((r.cell(c, seg).pct or 0) for c in r.categories)
        assert abs(total - 100.0) < 0.5


def test_show_not_answered_counts_per_banner_segment():
    """A banner classifier + `show_not_answered` used to raise KeyError: the
    per-segment missing counts were keyed off `data[classifying_var]`, and a
    banner's `classifying_var` is a QID, not a column. Passing the banner's own
    masks (the same segmentation `segment_bases`/`aggregate_counts` get) both
    fixes the crash and gives each member its real not-answered share.

    Pre-existing; repaired by the C2 fix, which makes every per-segment
    computation take the SAME segmentation. (2026-08-04 final review, C2)"""
    model, q, df = _setup(n=200)
    df = df.copy()
    df.loc[df["Polku1"].notna(), "q"] = None      # Polku 1 answered nothing
    r = engine.compute(q, _spec(show_not_answered=True), df, model)
    na = "Not answered"
    assert r.cell(na, "Polku 1").pct == 100.0
    assert r.cell(na, "Polku 2").pct == 0.0
    assert r.base_n["Total"] == 200
