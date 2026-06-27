"""Tests for Task B ChartSpec options: show_empty_categories, not_answered_codes,
category_label_overrides — model round-trip + deterministic engine behaviour."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    report_from_json,
    report_to_json,
)
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL, compute


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _var() -> Variable:
    """Categorical var with codes 1..3 (labelled), code 4 never used, 99 user-missing."""
    return Variable(
        name="q1",
        label="Satisfaction",
        measurement="categorical",
        value_labels=(
            ValueLabel(1.0, "Poor"),
            ValueLabel(2.0, "Fair"),
            ValueLabel(3.0, "Good"),
            ValueLabel(4.0, "Excellent"),   # never appears in data -> empty category
            ValueLabel(99.0, "En halua vastata"),
        ),
        missing_values=frozenset({99.0}),
    )


def _model() -> QuestionModel:
    var = _var()
    q = Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction")
    return QuestionModel(variables={"q1": var}, questions=[q])


def _data() -> pd.DataFrame:
    # 1:2, 2:3, 3:4, 4:0 valid; 99 x3 user-missing; NaN x2 sysmis
    return pd.DataFrame({
        "q1": [1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0, 3.0,
               99.0, 99.0, 99.0, np.nan, np.nan],
    })


def _spec(**kw) -> ChartSpec:
    return ChartSpec(
        question_ref="q1",
        chart_type=kw.get("chart_type", "horizontal_bar"),
        statistic=kw.get("statistic", "pct"),
        classifying_var=kw.get("classifying_var", None),
        number_format=kw.get("number_format", NumberFormat()),
        sort=kw.get("sort", SortSpec(basis="data_order")),
        template_slot="s1",
        elements=ElementToggles(),
        show_not_answered=kw.get("show_not_answered", False),
        show_empty_categories=kw.get("show_empty_categories", True),
        not_answered_codes=kw.get("not_answered_codes", None),
        category_label_overrides=kw.get("category_label_overrides", ()),
    )


def _base_chart(**kw) -> ChartSpec:
    return ChartSpec(
        question_ref="q1",
        chart_type="bar",
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="s1",
        elements=ElementToggles(),
        **kw,
    )


# ---------------------------------------------------------------------------
# Model round-trip
# ---------------------------------------------------------------------------


class TestModelRoundTrip:
    def test_defaults(self):
        c = _base_chart()
        assert c.show_empty_categories is True
        assert c.not_answered_codes is None
        assert c.category_label_overrides == ()

    def _round(self, chart: ChartSpec) -> ChartSpec:
        report = Report(name="R", render_mode="image", template_ref="t", charts=(chart,))
        return report_from_json(report_to_json(report)).charts[0]

    def test_show_empty_round_trips(self):
        assert self._round(_base_chart(show_empty_categories=False)).show_empty_categories is False
        assert self._round(_base_chart(show_empty_categories=True)).show_empty_categories is True

    def test_not_answered_codes_none_vs_empty_vs_value(self):
        assert self._round(_base_chart(not_answered_codes=None)).not_answered_codes is None
        assert self._round(_base_chart(not_answered_codes=())).not_answered_codes == ()
        got = self._round(_base_chart(not_answered_codes=(99.0,)))
        assert got.not_answered_codes == (99.0,)
        assert isinstance(got.not_answered_codes, tuple)

    def test_not_answered_codes_none_distinct_from_empty(self):
        # None survives as None; () survives as () — they are NOT collapsed.
        assert self._round(_base_chart(not_answered_codes=None)).not_answered_codes is None
        assert self._round(_base_chart(not_answered_codes=())).not_answered_codes == ()

    def test_missing_key_defaults(self):
        d = json.loads(report_to_json(
            Report(name="R", render_mode="image", template_ref="t", charts=(_base_chart(),))))
        for key in ("show_empty_categories", "not_answered_codes", "category_label_overrides"):
            del d["charts"][0][key]
        got = report_from_json(d).charts[0]
        assert got.show_empty_categories is True
        assert got.not_answered_codes is None
        assert got.category_label_overrides == ()

    def test_label_overrides_round_trip_from_pairs(self):
        got = self._round(_base_chart(category_label_overrides=(("Poor", "P"), ("Good", "G"))))
        assert got.category_label_overrides == (("Poor", "P"), ("Good", "G"))
        assert got.label_override_map() == {"Poor": "P", "Good": "G"}

    def test_label_overrides_parse_from_dict_json(self):
        d = json.loads(report_to_json(
            Report(name="R", render_mode="image", template_ref="t", charts=(_base_chart(),))))
        d["charts"][0]["category_label_overrides"] = {"Poor": "P", "Good": "G"}
        got = report_from_json(d).charts[0]
        assert got.label_override_map() == {"Poor": "P", "Good": "G"}

    def test_label_overrides_parse_from_list_of_lists_json(self):
        d = json.loads(report_to_json(
            Report(name="R", render_mode="image", template_ref="t", charts=(_base_chart(),))))
        d["charts"][0]["category_label_overrides"] = [["Poor", "P"], ["Good", "G"]]
        got = report_from_json(d).charts[0]
        assert got.category_label_overrides == (("Poor", "P"), ("Good", "G"))


# ---------------------------------------------------------------------------
# show_empty_categories
# ---------------------------------------------------------------------------


class TestHideEmpty:
    def test_empty_category_present_by_default(self):
        result = compute(_model().question("q1"), _spec(show_empty_categories=True),
                         _data(), _model())
        assert "Excellent" in result.categories  # 0 responses but shown

    def test_empty_category_dropped_when_false(self):
        result = compute(_model().question("q1"), _spec(show_empty_categories=False),
                         _data(), _model())
        assert "Excellent" not in result.categories
        assert set(result.categories) == {"Poor", "Fair", "Good"}

    def test_zero_not_answered_suppressed_when_hidden(self):
        # All-valid data -> 0 missing. With show_not_answered + hide-empty, NA bucket dropped.
        df = pd.DataFrame({"q1": [1.0, 2.0, 3.0]})
        result = compute(_model().question("q1"),
                         _spec(show_not_answered=True, show_empty_categories=False),
                         df, _model())
        assert NOT_ANSWERED_LABEL not in result.categories

    def test_zero_not_answered_kept_when_shown(self):
        df = pd.DataFrame({"q1": [1.0, 2.0, 3.0]})
        result = compute(_model().question("q1"),
                         _spec(show_not_answered=True, show_empty_categories=True),
                         df, _model())
        assert NOT_ANSWERED_LABEL in result.categories


# ---------------------------------------------------------------------------
# not_answered_codes
# ---------------------------------------------------------------------------


class TestNotAnsweredCodes:
    def test_default_none_uses_var_missing(self):
        # 99 is var-missing -> excluded from categories by default.
        result = compute(_model().question("q1"),
                         _spec(show_not_answered=True, not_answered_codes=None),
                         _data(), _model())
        # NA bucket count = 3 (code 99) + 2 (NaN) = 5
        assert result.cell(NOT_ANSWERED_LABEL, "Total").count == 5.0

    def test_explicit_codes_fold_value_into_not_answered(self):
        """not_answered_codes=(99,) folds 99 into NA; same as default here (99 is the missing)."""
        result = compute(_model().question("q1"),
                         _spec(show_not_answered=True, not_answered_codes=(99.0,)),
                         _data(), _model())
        assert result.cell(NOT_ANSWERED_LABEL, "Total").count == 5.0
        assert "En halua vastata" not in result.categories

    def test_fold_real_answer_code(self):
        """A real answer code (3) folded into NA: 3 no longer a normal category; base recomputes."""
        result = compute(_model().question("q1"),
                         _spec(show_not_answered=True, not_answered_codes=(3.0,)),
                         _data(), _model())
        # 3 ('Good') is now treated as not-answered, removed from normal categories.
        assert "Good" not in result.categories
        # NA count = 4 (code 3) + 2 (NaN) = 6  (99 is NOT in eff now -> counts as valid)
        assert result.cell(NOT_ANSWERED_LABEL, "Total").count == 6.0
        # En halua vastata (99) now a normal category since it's no longer in eff.
        assert "En halua vastata" in result.categories

    def test_empty_tuple_means_only_nan_is_missing(self):
        """not_answered_codes=() -> only NaN is missing; 99 becomes a normal category."""
        result = compute(_model().question("q1"),
                         _spec(show_not_answered=True, not_answered_codes=()),
                         _data(), _model())
        assert "En halua vastata" in result.categories
        # NA = only the 2 NaN rows
        assert result.cell(NOT_ANSWERED_LABEL, "Total").count == 2.0


# ---------------------------------------------------------------------------
# category_label_overrides
# ---------------------------------------------------------------------------


class TestLabelOverrides:
    def test_override_changes_display_not_order(self):
        spec = _spec(category_label_overrides=(("Good", "G!"),),
                     sort=SortSpec(basis="data_order"))
        result = compute(_model().question("q1"), spec, _data(), _model())
        assert "G!" in result.categories
        assert "Good" not in result.categories
        # order preserved (data_order): Poor, Fair, G!, Excellent
        assert list(result.categories).index("G!") == 2

    def test_override_does_not_affect_value_sort(self):
        # Sort by count descending; override the top category's label.
        spec = _spec(category_label_overrides=(("Good", "Top"),),
                     sort=SortSpec(basis="count", descending=True))
        result = compute(_model().question("q1"), spec, _data(), _model())
        # Good has the most responses (4) -> first even after rename.
        assert result.categories[0] == "Top"
        assert result.cell("Top", "Total").count == 4.0

    def test_not_answered_label_overridable(self):
        spec = _spec(show_not_answered=True,
                     category_label_overrides=((NOT_ANSWERED_LABEL, "EOS"),))
        result = compute(_model().question("q1"), spec, _data(), _model())
        assert "EOS" in result.categories
        assert NOT_ANSWERED_LABEL not in result.categories

    def test_not_answered_label_unchanged_without_override(self):
        spec = _spec(show_not_answered=True,
                     category_label_overrides=(("Poor", "P"),))
        result = compute(_model().question("q1"), spec, _data(), _model())
        assert NOT_ANSWERED_LABEL in result.categories
