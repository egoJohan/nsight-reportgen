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
import pytest

from reportbuilder.stats.engine import (
    NOT_ANSWERED_LABEL,
    TEXT_NOT_CHARTABLE_MSG,
    compute,
)


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
# Task G.4: hide categories whose DISPLAYED value rounds to 0
# ---------------------------------------------------------------------------


def _ident_model() -> QuestionModel:
    """var9-like identity question: Mieheksi/Naiseksi dominate; Muuksi/En halua
    sanoa are tiny-but-nonzero (display as 0 %)."""
    var = Variable(
        name="ident",
        label="Miten identifioit itsesi?",
        measurement="categorical",
        value_labels=(
            ValueLabel(1.0, "Mieheksi"),
            ValueLabel(2.0, "Naiseksi"),
            ValueLabel(3.0, "Muuksi"),
            ValueLabel(4.0, "En halua sanoa"),
        ),
        missing_values=frozenset(),
    )
    q = Question(qid="ident", kind="single", variables=("ident",), text="Identity")
    return QuestionModel(variables={"ident": var}, questions=[q])


def _ident_data() -> pd.DataFrame:
    # n = 1001: Mieheksi 500, Naiseksi 496, Muuksi 4 (0.40%), En halua sanoa 1 (0.10%)
    codes = [1.0] * 500 + [2.0] * 496 + [3.0] * 4 + [4.0] * 1
    return pd.DataFrame({"ident": codes})


def _ident_spec(**kw) -> ChartSpec:
    return ChartSpec(
        question_ref="ident",
        chart_type="pie",
        statistic=kw.get("statistic", "pct"),
        classifying_var=None,
        number_format=kw.get("number_format", NumberFormat()),
        sort=SortSpec(basis="data_order"),
        template_slot="s1",
        elements=ElementToggles(),
        show_empty_categories=kw.get("show_empty_categories", True),
    )


class TestHideDisplayZero:
    def test_display_zero_categories_dropped_when_false(self):
        """Muuksi (4/1001 -> "0 %") and En halua sanoa (1/1001 -> "0 %") are
        dropped though their counts are non-zero; Mieheksi/Naiseksi remain."""
        result = compute(_ident_model().question("ident"),
                         _ident_spec(show_empty_categories=False),
                         _ident_data(), _ident_model())
        assert set(result.categories) == {"Mieheksi", "Naiseksi"}
        assert "Muuksi" not in result.categories
        assert "En halua sanoa" not in result.categories

    def test_display_zero_categories_kept_when_true(self):
        result = compute(_ident_model().question("ident"),
                         _ident_spec(show_empty_categories=True),
                         _ident_data(), _ident_model())
        assert "Muuksi" in result.categories
        assert "En halua sanoa" in result.categories

    def test_one_decimal_nonzero_pct_is_kept(self):
        """With a manual 1-decimal format, Muuksi shows "0.4 %" (NOT zero as
        displayed) and must be kept; En halua sanoa shows "0.1 %" and kept too."""
        result = compute(_ident_model().question("ident"),
                         _ident_spec(show_empty_categories=False,
                                     number_format=NumberFormat(mode="manual", pct_decimals=1)),
                         _ident_data(), _ident_model())
        assert "Muuksi" in result.categories            # 0.4 % is not displayed-zero
        assert result.cell("Muuksi", "Total").pct == 0.4
        assert "En halua sanoa" in result.categories    # 0.1 %


# ---------------------------------------------------------------------------
# Task G.3: open-ended text questions raise a clean, actionable error
# ---------------------------------------------------------------------------


class TestTextQuestionGuard:
    def _text_model(self) -> QuestionModel:
        var = Variable(name="other", label="Muut, mitkä?", measurement="text",
                       value_labels=(), missing_values=frozenset())
        q = Question(qid="other", kind="single", variables=("other",), text="Muut, mitkä?")
        return QuestionModel(variables={"other": var}, questions=[q])

    def test_compute_on_text_question_raises_clear_value_error(self):
        model = self._text_model()
        df = pd.DataFrame({"other": ["Alzheimer potilas", "kotihoito", "x"]})
        with pytest.raises(ValueError) as exc:
            compute(model.question("other"), _spec(), df, model)
        msg = str(exc.value)
        assert msg == TEXT_NOT_CHARTABLE_MSG
        assert "could not convert string to float" not in msg


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


# ---------------------------------------------------------------------------
# Regression: not_answered_codes must drive the percentage BASE (eff-aware)
#
# Defect: not_answered_codes was applied when counting the "Not answered"
# bucket but NOT when computing the percentage base/denominator. When the
# chosen codes diverge from var.missing_values the percentages were silently
# wrong (denominator could even exceed N). The base (single_base /
# segment_bases) must honour the effective not-answered set.
# ---------------------------------------------------------------------------


class TestNotAnsweredCodesDriveBase:
    """Divergent not_answered_codes=(3.0,) vs var.missing_values={99.0}.

    Data N=14: code1 x2, code2 x3, code3 x4, code99 x3, NaN x2.
    With eff={3.0}: valid (non-NaN, not in eff) = 2+3+3 = 8 (99 counts valid),
    not-answered bucket = code3(4)+NaN(2) = 6. denom(show_na) = 8+6 = 14 == N.
    """

    def test_show_na_denom_equals_n_no_double_count(self):
        spec = _spec(show_not_answered=True, not_answered_codes=(3.0,),
                     number_format=NumberFormat(pct_decimals=1))
        result = compute(_model().question("q1"), spec, _data(), _model())
        # denom == N (14): valid(8) + missing(6), no double-count, no drop.
        assert result.base_n["Total"] == 14
        # "Not answered" = 6/14 = 42.9% (NOT 6/15 and NOT 43% from a wrong base).
        assert result.cell(NOT_ANSWERED_LABEL, "Total").count == 6.0
        assert result.cell(NOT_ANSWERED_LABEL, "Total").pct == 42.9

    def test_show_na_category_percentages_use_eff_base(self):
        spec = _spec(show_not_answered=True, not_answered_codes=(3.0,),
                     number_format=NumberFormat(pct_decimals=1))
        result = compute(_model().question("q1"), spec, _data(), _model())
        # All shown-category percentages computed over base==14.
        assert result.cell("Poor", "Total").pct == round(2 / 14 * 100, 1)   # 14.3
        assert result.cell("Fair", "Total").pct == round(3 / 14 * 100, 1)   # 21.4
        # 99 is NOT in eff now -> a normal category, pct over base 14.
        assert result.cell("En halua vastata", "Total").pct == round(3 / 14 * 100, 1)
        # Folded code 3 is gone from normal categories.
        assert "Good" not in result.categories
        # Percentages (incl. Not answered) sum to 100 over the eff-aware base.
        shown = result.categories
        total_pct = sum(result.cell(c, "Total").pct for c in shown)
        assert total_pct == 100.0

    def test_show_na_false_uses_eff_base_for_shown_categories(self):
        # show_not_answered=False: eff codes excluded from categories AND the
        # base for the SHOWN categories' percentages must be the eff-aware
        # valid count (8), not the var.missing_values count (10).
        spec = _spec(show_not_answered=False, not_answered_codes=(3.0,),
                     number_format=NumberFormat(pct_decimals=1))
        result = compute(_model().question("q1"), spec, _data(), _model())
        assert "Good" not in result.categories            # eff code excluded
        assert NOT_ANSWERED_LABEL not in result.categories
        assert result.base_n["Total"] == 8                # eff-aware base
        assert result.cell("Poor", "Total").pct == round(2 / 8 * 100, 1)   # 25.0
        assert result.cell("En halua vastata", "Total").pct == round(3 / 8 * 100, 1)  # 37.5

    def test_default_path_base_unchanged(self):
        # not_answered_codes=None -> eff == var.missing_values ({99}); base
        # behaviour must be byte-identical to the legacy default.
        spec = _spec(show_not_answered=True, not_answered_codes=None,
                     number_format=NumberFormat(pct_decimals=1))
        result = compute(_model().question("q1"), spec, _data(), _model())
        # valid (non-NaN, not 99) = 2+3+4 = 9; missing = 99(3)+NaN(2) = 5; denom 14.
        assert result.base_n["Total"] == 14
        assert result.cell(NOT_ANSWERED_LABEL, "Total").count == 5.0
        assert result.cell("Good", "Total").pct == round(4 / 14 * 100, 1)   # 28.6


class TestNotAnsweredCodesDriveSegmentBase:
    """Segmented (classifying_var) case: segment_bases must honour the override."""

    def _seg_model(self) -> QuestionModel:
        var = _var()
        q = Question(qid="q1", kind="single", variables=("q1",), text="Satisfaction")
        return QuestionModel(variables={"q1": var}, questions=[q])

    def _seg_data(self) -> pd.DataFrame:
        # q1 matches _data(); seg in {1,2}. With eff={3.0}:
        #   valid (non-NaN, q1!=3): rows with q1 in {1,2,99}
        #   seg1 valid -> 5, seg2 valid -> 3, Total -> 8
        # The OLD (buggy) var.missing_values={99} base would give seg1=5,
        # seg2=4, Total=9 -> the assertions below distinguish the two.
        return pd.DataFrame({
            "q1":  [1.0, 1.0, 2.0, 2.0, 2.0, 3.0, 3.0, 3.0, 3.0,
                    99.0, 99.0, 99.0, np.nan, np.nan],
            "seg": [1.0, 2.0, 1.0, 2.0, 1.0, 1.0, 2.0, 1.0, 2.0,
                    1.0, 2.0, 1.0, 1.0, 2.0],
        })

    def test_segment_bases_are_eff_aware(self):
        spec = _spec(classifying_var="seg", show_not_answered=False,
                     not_answered_codes=(3.0,),
                     number_format=NumberFormat(pct_decimals=1))
        result = compute(self._seg_model().question("q1"), spec,
                         self._seg_data(), self._seg_model())
        # eff-aware per-segment bases (NOT the buggy 9/5/4).
        assert result.base_n["Total"] == 8
        assert result.base_n["1"] == 5
        assert result.base_n["2"] == 3
        # Percentages computed over the eff-aware per-segment base.
        # Poor(code1): seg1 has 1 -> 1/5; Fair(code2): seg2 has 1 -> 1/3.
        assert result.cell("Poor", "1").count == 1.0
        assert result.cell("Poor", "1").pct == round(1 / 5 * 100, 1)   # 20.0
        assert result.cell("Fair", "2").pct == round(1 / 3 * 100, 1)   # 33.3

    def test_segment_show_na_denom_equals_segment_n(self):
        # With show_not_answered the per-segment denom = valid + missing in seg.
        # seg1: valid 5 + missing(code3 idx5,7 + NaN idx12)=3 -> 8
        # seg2: valid 3 + missing(code3 idx6,8 + NaN idx13)=3 -> 6
        spec = _spec(classifying_var="seg", show_not_answered=True,
                     not_answered_codes=(3.0,),
                     number_format=NumberFormat(pct_decimals=1))
        result = compute(self._seg_model().question("q1"), spec,
                         self._seg_data(), self._seg_model())
        assert result.base_n["1"] == 8
        assert result.base_n["2"] == 6
        assert result.base_n["Total"] == 14
        assert result.cell(NOT_ANSWERED_LABEL, "1").pct == round(3 / 8 * 100, 1)  # 37.5
        assert result.cell(NOT_ANSWERED_LABEL, "2").pct == round(3 / 6 * 100, 1)  # 50.0
