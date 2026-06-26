"""Tests for the "Not answered" feature — Task A6.

Covers:
- QuestionModel.missing_value_labels() returns (code, label) for user-missing codes. (REQ-D-06)
- Engine _single with show_not_answered=False: base excludes missing (unchanged). (REQ-MV-01, REQ-MV-02)
- Engine _single with show_not_answered=True: "Not answered" category present, count == missing
  respondents, base == total, all pcts sum ≈ 100. (REQ-D-06, REQ-MV-01, REQ-MV-02)
- ChartSpec.show_not_answered round-trips through JSON (default False).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from reportbuilder.model.question import Question, QuestionModel, ValueLabel, Variable
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    SortSpec,
    report_from_json,
    report_to_json,
    Report,
)
from reportbuilder.stats.engine import NOT_ANSWERED_LABEL, compute


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _var_with_missing() -> Variable:
    """A categorical variable with user-missing code 99 = 'En tiedä'. (REQ-D-06)"""
    return Variable(
        name="q1",
        label="Satisfaction",
        measurement="categorical",
        value_labels=(
            ValueLabel(1.0, "Poor"),
            ValueLabel(2.0, "Fair"),
            ValueLabel(3.0, "Good"),
            ValueLabel(99.0, "En tiedä"),        # user-missing, labelled
        ),
        missing_values=frozenset({99.0}),
    )


def _model_with_missing() -> QuestionModel:
    var = _var_with_missing()
    q = Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction")
    return QuestionModel(variables={"q1": var}, questions=[q])


def _spec(show_not_answered: bool = False, **kw) -> ChartSpec:
    return ChartSpec(
        question_ref="q1",
        chart_type=kw.get("chart_type", "horizontal_bar"),
        statistic=kw.get("statistic", "pct"),
        classifying_var=kw.get("classifying_var", None),
        number_format=kw.get("number_format", NumberFormat()),
        sort=kw.get("sort", SortSpec(basis="data_order")),
        template_slot=kw.get("template_slot", "s1"),
        elements=kw.get("elements", ElementToggles()),
        show_not_answered=show_not_answered,
    )


def _data_with_missing() -> pd.DataFrame:
    """10 valid + 3 user-missing (99) + 2 sysmis (NaN) = 15 total respondents."""
    return pd.DataFrame({
        "q1": [1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 3.0, 1.0, 2.0, 3.0,
               99.0, 99.0, 99.0, np.nan, np.nan],
    })


# ---------------------------------------------------------------------------
# Tests: QuestionModel.missing_value_labels()
# ---------------------------------------------------------------------------

class TestMissingValueLabels:
    def test_returns_code_label_pairs(self):
        """missing_value_labels returns (float, str) pairs for user-missing codes. (REQ-D-06)"""
        model = _model_with_missing()
        result = model.missing_value_labels("q1")
        assert result == [(99.0, "En tiedä")]

    def test_returns_empty_when_no_missing(self):
        """Returns empty list when the variable has no user-missing codes. (REQ-D-06)"""
        var = Variable(
            name="q2", label="Q2", measurement="categorical",
            value_labels=(ValueLabel(1.0, "Yes"), ValueLabel(2.0, "No")),
            missing_values=frozenset(),
        )
        q = Question(qid="q2", kind="single", variables=("q2",), text="Q2")
        model = QuestionModel(variables={"q2": var}, questions=[q])
        assert model.missing_value_labels("q2") == []

    def test_falls_back_to_code_string_when_no_label(self):
        """Falls back to the code as a string when value_labels has no entry. (REQ-D-06)"""
        var = Variable(
            name="q3", label="Q3", measurement="categorical",
            value_labels=(ValueLabel(1.0, "Yes"),),   # 88 is missing but unlabelled
            missing_values=frozenset({88.0}),
        )
        q = Question(qid="q3", kind="single", variables=("q3",), text="Q3")
        model = QuestionModel(variables={"q3": var}, questions=[q])
        result = model.missing_value_labels("q3")
        assert result == [(88.0, "88")]

    def test_multiple_missing_codes_sorted(self):
        """Multiple user-missing codes are returned sorted ascending. (REQ-D-06)"""
        var = Variable(
            name="q4", label="Q4", measurement="categorical",
            value_labels=(
                ValueLabel(1.0, "Yes"),
                ValueLabel(97.0, "Refused"),
                ValueLabel(98.0, "Don't know"),
                ValueLabel(99.0, "NA"),
            ),
            missing_values=frozenset({97.0, 98.0, 99.0}),
        )
        q = Question(qid="q4", kind="single", variables=("q4",), text="Q4")
        model = QuestionModel(variables={"q4": var}, questions=[q])
        result = model.missing_value_labels("q4")
        assert result == [(97.0, "Refused"), (98.0, "Don't know"), (99.0, "NA")]


# ---------------------------------------------------------------------------
# Tests: engine with show_not_answered=False (unchanged behavior)
# ---------------------------------------------------------------------------

class TestEngineExcludesMissing:
    def test_base_excludes_user_missing_and_sysmis(self):
        """Default: base excludes user-missing + sysmis; 'Not answered' absent. (REQ-MV-01, REQ-MV-02)"""
        model = _model_with_missing()
        q = model.question("q1")
        df = _data_with_missing()   # 10 valid, 5 missing total

        result = compute(q, _spec(show_not_answered=False), df, model)

        assert result.base_n["Total"] == 10, "Valid base must exclude all missing"
        assert NOT_ANSWERED_LABEL not in result.categories, "'Not answered' must not appear"

    def test_pcts_sum_to_100_over_valid_base(self):
        """Percentages sum to 100 over the valid base when show_not_answered=False. (REQ-MV-01)"""
        model = _model_with_missing()
        q = model.question("q1")
        df = _data_with_missing()

        result = compute(q, _spec(show_not_answered=False), df, model)

        total_pct = sum(result.cell(c, "Total").pct for c in result.categories)
        assert abs(total_pct - 100.0) < 0.5, f"Pcts should sum to ~100, got {total_pct}"


# ---------------------------------------------------------------------------
# Tests: engine with show_not_answered=True
# ---------------------------------------------------------------------------

class TestEngineShowNotAnswered:
    def test_not_answered_category_present(self):
        """'Not answered' category appears when show_not_answered=True. (REQ-D-06, REQ-MV-01)"""
        model = _model_with_missing()
        q = model.question("q1")
        df = _data_with_missing()

        result = compute(q, _spec(show_not_answered=True), df, model)

        assert NOT_ANSWERED_LABEL in result.categories

    def test_not_answered_is_last_category(self):
        """'Not answered' is placed after all real categories. (REQ-D-06)"""
        model = _model_with_missing()
        q = model.question("q1")
        df = _data_with_missing()

        result = compute(q, _spec(show_not_answered=True), df, model)

        assert result.categories[-1] == NOT_ANSWERED_LABEL

    def test_not_answered_count_equals_missing_respondents(self):
        """'Not answered' count == user-missing + sysmis respondents. (REQ-MV-01, REQ-MV-02)"""
        model = _model_with_missing()
        q = model.question("q1")
        df = _data_with_missing()   # 3 user-missing + 2 sysmis = 5 missing

        result = compute(q, _spec(show_not_answered=True), df, model)

        na_cell = result.cell(NOT_ANSWERED_LABEL, "Total")
        assert na_cell.count == 5.0, f"Expected 5 missing, got {na_cell.count}"

    def test_base_equals_total_respondents(self):
        """base_n['Total'] == total respondents (valid + missing) when show_not_answered=True. (REQ-MV-01)"""
        model = _model_with_missing()
        q = model.question("q1")
        df = _data_with_missing()   # 10 valid + 5 missing = 15 total

        result = compute(q, _spec(show_not_answered=True), df, model)

        assert result.base_n["Total"] == 15, f"Expected 15 total, got {result.base_n['Total']}"

    def test_all_pcts_sum_to_100(self):
        """All category pcts (including 'Not answered') sum to ~100 (within rounding). (REQ-D-06, REQ-MV-01)"""
        model = _model_with_missing()
        q = model.question("q1")
        df = _data_with_missing()

        result = compute(q, _spec(show_not_answered=True), df, model)

        total_pct = sum(result.cell(c, "Total").pct for c in result.categories)
        # Allow ≤ 1 pp rounding error — integer-rounded percentages may not sum exactly to 100.
        assert abs(total_pct - 100.0) <= 1.0, f"Pcts should sum to ~100 (±1 pp rounding), got {total_pct}"

    def test_real_categories_still_present(self):
        """Real categories (not missing) still appear alongside 'Not answered'. (REQ-D-06)"""
        model = _model_with_missing()
        q = model.question("q1")
        df = _data_with_missing()

        result = compute(q, _spec(show_not_answered=True), df, model)

        real_cats = [c for c in result.categories if c != NOT_ANSWERED_LABEL]
        assert set(real_cats) == {"Poor", "Fair", "Good"}

    def test_no_missing_respondents_not_answered_zero(self):
        """When all rows are valid, 'Not answered' count == 0 and pct == 0. (REQ-D-06)"""
        model = _model_with_missing()
        q = model.question("q1")
        # No missing at all
        df = pd.DataFrame({"q1": [1.0, 2.0, 3.0, 1.0, 2.0]})

        result = compute(q, _spec(show_not_answered=True), df, model)

        na_cell = result.cell(NOT_ANSWERED_LABEL, "Total")
        assert na_cell.count == 0.0
        assert na_cell.pct == 0.0
        assert result.base_n["Total"] == 5


# ---------------------------------------------------------------------------
# Tests: ChartSpec.show_not_answered round-trip
# ---------------------------------------------------------------------------

class TestChartSpecShowNotAnsweredRoundTrip:
    def _make_chart(self, show_not_answered: bool) -> ChartSpec:
        return ChartSpec(
            question_ref="q1",
            chart_type="horizontal_bar",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="data_order"),
            template_slot="s1",
            elements=ElementToggles(),
            show_not_answered=show_not_answered,
        )

    def test_default_is_false(self):
        """show_not_answered defaults to False. (REQ-D-06)"""
        spec = ChartSpec(
            question_ref="q1",
            chart_type="horizontal_bar",
            statistic="pct",
            classifying_var=None,
            number_format=NumberFormat(),
            sort=SortSpec(basis="data_order"),
            template_slot="s1",
            elements=ElementToggles(),
        )
        assert spec.show_not_answered is False

    def test_round_trip_false(self):
        """show_not_answered=False survives JSON round-trip. (REQ-D-06)"""
        report = Report(
            name="R", render_mode="native", template_ref="t.pptx",
            charts=(self._make_chart(False),),
        )
        result = report_from_json(report_to_json(report))
        assert result.charts[0].show_not_answered is False

    def test_round_trip_true(self):
        """show_not_answered=True survives JSON round-trip. (REQ-D-06)"""
        report = Report(
            name="R", render_mode="native", template_ref="t.pptx",
            charts=(self._make_chart(True),),
        )
        result = report_from_json(report_to_json(report))
        assert result.charts[0].show_not_answered is True

    def test_missing_key_in_json_defaults_to_false(self):
        """Old JSON without 'show_not_answered' key deserialises as False. (REQ-D-06)"""
        report = Report(
            name="R", render_mode="native", template_ref="t.pptx",
            charts=(self._make_chart(False),),
        )
        d = json.loads(report_to_json(report))
        # Remove the key from the JSON to simulate an old serialized report
        del d["charts"][0]["show_not_answered"]
        result = report_from_json(d)
        assert result.charts[0].show_not_answered is False
