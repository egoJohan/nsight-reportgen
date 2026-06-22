"""Tests for Report JSON (de)serialization (Task 0.9)."""
import json
import pytest

from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    report_from_json,
    report_to_json,
)


def _make_report() -> Report:
    chart_a = ChartSpec(
        question_ref="q1",
        chart_type="bar",
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="pct"),
        template_slot="slot_a",
        elements=ElementToggles(),
        scatter_xy=None,
    )
    chart_b = ChartSpec(
        question_ref="q2",
        chart_type="column",
        statistic="pct",
        classifying_var="region",
        number_format=NumberFormat(pct_decimals=1),
        sort=SortSpec(basis="topbox_sum", topbox_codes=(4.0, 5.0)),
        template_slot="slot_b",
        elements=ElementToggles(legend=False),
        scatter_xy=None,
    )
    chart_c = ChartSpec(
        question_ref="q3",
        chart_type="scatter",
        statistic="mean",
        classifying_var=None,
        number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"),
        template_slot="slot_c",
        elements=ElementToggles(),
        scatter_xy=("satisfaction", "loyalty"),
    )
    return Report(
        name="Test Report",
        render_mode="native",
        template_ref="tmpl_001",
        charts=(chart_a, chart_b, chart_c),
    )


def test_round_trip_equality():
    """Full round-trip: report_from_json(report_to_json(r)) == r."""
    r = _make_report()
    assert report_from_json(report_to_json(r)) == r


def test_to_json_produces_valid_json_string():
    """report_to_json returns a str that parses as valid JSON."""
    r = _make_report()
    result = report_to_json(r)
    assert isinstance(result, str)
    parsed = json.loads(result)
    assert isinstance(parsed, dict)


def test_from_json_accepts_parsed_dict():
    """report_from_json accepts an already-parsed dict."""
    r = _make_report()
    parsed_dict = json.loads(report_to_json(r))
    result = report_from_json(parsed_dict)
    assert result == r


def test_tuples_restored_after_round_trip():
    """topbox_codes and scatter_xy are tuples (not lists) after round-trip."""
    r = _make_report()
    result = report_from_json(report_to_json(r))
    assert result.charts[1].sort.topbox_codes == (4.0, 5.0)
    assert isinstance(result.charts[1].sort.topbox_codes, tuple)
    assert result.charts[2].scatter_xy == ("satisfaction", "loyalty")
    assert isinstance(result.charts[2].scatter_xy, tuple)
