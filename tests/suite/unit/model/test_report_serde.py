"""Unit tests for reportbuilder.model.report — serde + helpers.

Deterministic; no network/soffice. Asserts the REAL round-trip and canonical
serialization behavior, the critical not_answered_codes tri-state invariant,
label-override normalization, and the special-slide helpers.
"""
from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace

import pytest

from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    SPECIAL_SLIDE_TYPES,
    is_demographics_grid,
    is_special_slide,
    renders_as_bullets,
    report_from_json,
    report_to_json,
)
from reportbuilder.testing.fixtures import (
    _chart,
    one_chart_report,
    report_json_n_charts,
    two_chart_report,
)


def _report(chart: ChartSpec) -> Report:
    return Report(name="R", render_mode="native", template_ref="t.pptx", charts=(chart,))


# ---- dataclass defaults & frozen -------------------------------------------

def test_sortspec_defaults():
    s = SortSpec(basis="pct")
    assert s.topbox_codes == ()
    assert s.descending is True


def test_numberformat_defaults():
    nf = NumberFormat()
    assert nf.mode == "auto"
    assert nf.pct_decimals == 0
    assert nf.mean_decimals == 1
    assert nf.count_round_up is False
    assert nf.show_pct_sign is True


def test_elementtoggles_all_true_by_default():
    el = ElementToggles()
    assert all([el.title, el.legend, el.n, el.axis_names, el.filter_var, el.data_labels])


def test_chartspec_defaults():
    c = _chart()
    assert c.scatter_xy is None
    assert c.show_not_answered is False
    assert c.slide_title is None
    assert c.slide_description is None
    assert c.show_empty_categories is True
    assert c.not_answered_codes is None
    assert c.category_label_overrides == ()
    assert c.options == {}


def test_report_is_frozen():
    r = one_chart_report()
    with pytest.raises(FrozenInstanceError):
        r.name = "other"  # type: ignore[misc]


def test_chartspec_is_frozen():
    c = _chart()
    with pytest.raises(FrozenInstanceError):
        c.statistic = "count"  # type: ignore[misc]


# ---- canonical / deterministic serialization -------------------------------

def test_report_to_json_returns_valid_json():
    s = report_to_json(one_chart_report())
    parsed = json.loads(s)
    assert parsed["name"] == "R1"
    assert isinstance(parsed["charts"], list)


def test_report_to_json_is_deterministic():
    r = two_chart_report()
    assert report_to_json(r) == report_to_json(r)


def test_report_to_json_is_sorted_keys():
    s = report_to_json(one_chart_report())
    parsed = json.loads(s)
    assert list(parsed.keys()) == sorted(parsed.keys())
    assert list(parsed["charts"][0].keys()) == sorted(parsed["charts"][0].keys())


def test_report_to_json_preserves_non_ascii():
    r = _report(replace(_chart(), slide_title="Tyytyväisyys ä ö"))
    s = report_to_json(r)
    # ensure_ascii=False -> literal characters survive, not \uXXXX escapes
    assert "Tyytyväisyys ä ö" in s
    assert "\\u" not in s


def test_tuples_become_json_arrays():
    parsed = json.loads(report_to_json(two_chart_report()))
    assert isinstance(parsed["charts"], list)
    assert len(parsed["charts"]) == 2


# ---- round-trip equality ---------------------------------------------------

def test_round_trip_from_string_reconstructs_equal_report():
    r = two_chart_report()
    assert report_from_json(report_to_json(r)) == r


def test_round_trip_accepts_dict():
    r = one_chart_report()
    as_dict = json.loads(report_to_json(r))
    assert report_from_json(as_dict) == r


def test_round_trip_accepts_string():
    r = one_chart_report()
    assert report_from_json(report_to_json(r)) == r


def test_round_trip_via_fixture_dict_helper():
    d = report_json_n_charts(3)
    r = report_from_json(d)
    assert len(r.charts) == 3
    assert r.name == "R-3"


def test_round_trip_restores_charts_as_tuple():
    r = report_from_json(report_to_json(two_chart_report()))
    assert isinstance(r.charts, tuple)


def test_round_trip_restores_topbox_codes_as_tuple():
    c = replace(_chart(), sort=SortSpec(basis="topbox_sum", topbox_codes=(4.0, 5.0)))
    r = report_from_json(report_to_json(_report(c)))
    assert r.charts[0].sort.topbox_codes == (4.0, 5.0)
    assert isinstance(r.charts[0].sort.topbox_codes, tuple)


def test_round_trip_preserves_nested_numberformat():
    nf = NumberFormat(mode="manual", pct_decimals=2, mean_decimals=3,
                      count_round_up=True, show_pct_sign=False)
    r = report_from_json(report_to_json(_report(replace(_chart(), number_format=nf))))
    assert r.charts[0].number_format == nf


def test_round_trip_preserves_element_toggles():
    el = ElementToggles(title=False, legend=False, n=True, axis_names=False,
                        filter_var=True, data_labels=False)
    r = report_from_json(report_to_json(_report(replace(_chart(), elements=el))))
    assert r.charts[0].elements == el


def test_round_trip_preserves_options_dict():
    c = replace(_chart(), options={"bullets": ["a", "b"], "k": 1})
    r = report_from_json(report_to_json(_report(c)))
    assert r.charts[0].options == {"bullets": ["a", "b"], "k": 1}


# ---- defaults applied when keys omitted ------------------------------------

def test_missing_numberformat_keys_use_defaults():
    d = json.loads(report_to_json(one_chart_report()))
    d["charts"][0]["number_format"] = {}  # all keys omitted
    r = report_from_json(d)
    assert r.charts[0].number_format == NumberFormat()


def test_missing_sort_optional_keys_use_defaults():
    d = json.loads(report_to_json(one_chart_report()))
    d["charts"][0]["sort"] = {"basis": "pct"}  # topbox_codes / descending omitted
    r = report_from_json(d)
    assert r.charts[0].sort == SortSpec(basis="pct")


def test_missing_optional_chart_keys_use_defaults():
    d = json.loads(report_to_json(one_chart_report()))
    for k in ["show_not_answered", "slide_title", "slide_description",
              "show_empty_categories", "not_answered_codes",
              "category_label_overrides", "options", "scatter_xy",
              "classifying_var"]:
        d["charts"][0].pop(k, None)
    r = report_from_json(d)
    c = r.charts[0]
    assert c.show_not_answered is False
    assert c.slide_title is None
    assert c.slide_description is None
    assert c.show_empty_categories is True
    assert c.not_answered_codes is None
    assert c.category_label_overrides == ()
    assert c.options == {}
    assert c.scatter_xy is None
    assert c.classifying_var is None


# ---- not_answered_codes tri-state invariant --------------------------------

def test_not_answered_codes_none_stays_none():
    c = replace(_chart(), not_answered_codes=None)
    r = report_from_json(report_to_json(_report(c)))
    assert r.charts[0].not_answered_codes is None


def test_not_answered_codes_empty_tuple_stays_empty_tuple():
    c = replace(_chart(), not_answered_codes=())
    r = report_from_json(report_to_json(_report(c)))
    assert r.charts[0].not_answered_codes == ()
    assert r.charts[0].not_answered_codes is not None


def test_not_answered_codes_populated_round_trips():
    c = replace(_chart(), not_answered_codes=(10054.0, 10055.0))
    r = report_from_json(report_to_json(_report(c)))
    assert r.charts[0].not_answered_codes == (10054.0, 10055.0)
    assert isinstance(r.charts[0].not_answered_codes, tuple)


def test_not_answered_codes_three_states_are_distinct():
    none_r = report_from_json(report_to_json(_report(replace(_chart(), not_answered_codes=None))))
    empty_r = report_from_json(report_to_json(_report(replace(_chart(), not_answered_codes=()))))
    full_r = report_from_json(report_to_json(_report(replace(_chart(), not_answered_codes=(1.0,)))))
    values = [
        none_r.charts[0].not_answered_codes,
        empty_r.charts[0].not_answered_codes,
        full_r.charts[0].not_answered_codes,
    ]
    assert values == [None, (), (1.0,)]
    # all three genuinely distinct
    assert len({repr(v) for v in values}) == 3


def test_not_answered_codes_absent_key_is_none():
    d = json.loads(report_to_json(one_chart_report()))
    d["charts"][0].pop("not_answered_codes", None)
    assert report_from_json(d).charts[0].not_answered_codes is None


def test_not_answered_codes_explicit_null_is_none():
    d = json.loads(report_to_json(one_chart_report()))
    d["charts"][0]["not_answered_codes"] = None
    assert report_from_json(d).charts[0].not_answered_codes is None


# ---- category_label_overrides / label_override_map -------------------------

def test_label_override_map_from_pairs():
    c = replace(_chart(), category_label_overrides=(("Full label", "Short"),))
    assert c.label_override_map() == {"Full label": "Short"}


def test_label_override_map_empty():
    assert _chart().label_override_map() == {}


def test_label_overrides_round_trip_from_tuple_pairs():
    c = replace(_chart(), category_label_overrides=(("A long one", "A"), ("Bee", "B")))
    r = report_from_json(report_to_json(_report(c)))
    assert r.charts[0].label_override_map() == {"A long one": "A", "Bee": "B"}


def test_label_overrides_accepts_dict_input():
    d = json.loads(report_to_json(one_chart_report()))
    d["charts"][0]["category_label_overrides"] = {"Full": "Sh"}
    r = report_from_json(d)
    assert r.charts[0].label_override_map() == {"Full": "Sh"}
    assert r.charts[0].category_label_overrides == (("Full", "Sh"),)


def test_label_overrides_accepts_list_of_pairs_input():
    d = json.loads(report_to_json(one_chart_report()))
    d["charts"][0]["category_label_overrides"] = [["Alpha", "A"], ["Beta", "B"]]
    r = report_from_json(d)
    assert r.charts[0].label_override_map() == {"Alpha": "A", "Beta": "B"}


def test_label_overrides_coerces_values_to_str():
    d = json.loads(report_to_json(one_chart_report()))
    d["charts"][0]["category_label_overrides"] = {1: 2}
    r = report_from_json(d)
    assert r.charts[0].category_label_overrides == (("1", "2"),)


# ---- scatter_xy ------------------------------------------------------------

def test_scatter_xy_round_trips_to_tuple():
    c = replace(_chart(), scatter_xy=("q1", "age"))
    r = report_from_json(report_to_json(_report(c)))
    assert r.charts[0].scatter_xy == ("q1", "age")
    assert isinstance(r.charts[0].scatter_xy, tuple)


def test_scatter_xy_none_stays_none():
    r = report_from_json(report_to_json(one_chart_report()))
    assert r.charts[0].scatter_xy is None


def test_scatter_xy_absent_key_is_none():
    d = json.loads(report_to_json(one_chart_report()))
    d["charts"][0].pop("scatter_xy", None)
    assert report_from_json(d).charts[0].scatter_xy is None


# ---- special-slide helpers -------------------------------------------------

def test_special_slide_types_membership():
    assert SPECIAL_SLIDE_TYPES == frozenset(
        {"special_overview", "special_conclusion", "special_demographics"}
    )


@pytest.mark.parametrize("ct", sorted(SPECIAL_SLIDE_TYPES))
def test_is_special_slide_true_for_special_types(ct):
    assert is_special_slide(replace(_chart(), chart_type=ct)) is True


def test_is_special_slide_false_for_bar():
    assert is_special_slide(replace(_chart(), chart_type="vertical_bar")) is False


def test_is_special_slide_false_for_themes():
    assert is_special_slide(replace(_chart(), chart_type="themes")) is False


@pytest.mark.parametrize("ct", sorted(SPECIAL_SLIDE_TYPES) + ["themes"])
def test_renders_as_bullets_true_for_bullet_types(ct):
    assert renders_as_bullets(replace(_chart(), chart_type=ct)) is True


def test_renders_as_bullets_false_for_bar():
    assert renders_as_bullets(replace(_chart(), chart_type="vertical_bar")) is False


def test_renders_as_bullets_false_for_demographics_grid():
    assert renders_as_bullets(replace(_chart(), chart_type="demographics_grid")) is False


def test_is_demographics_grid_true():
    assert is_demographics_grid(replace(_chart(), chart_type="demographics_grid")) is True


def test_is_demographics_grid_false_for_bar():
    assert is_demographics_grid(replace(_chart(), chart_type="vertical_bar")) is False


def test_is_demographics_grid_false_for_special_demographics():
    """The special text slide is NOT the multi-chart grid."""
    assert is_demographics_grid(replace(_chart(), chart_type="special_demographics")) is False
