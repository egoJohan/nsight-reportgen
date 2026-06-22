"""Tests for reports routes: POST/PUT/GET/DELETE + duplicate. (REQ-C-08/09/10/11/12)"""
import json
from unittest.mock import Mock

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    report_from_json,
    report_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_chart(question_ref: str, chart_type: str = "bar") -> ChartSpec:
    """Build a fully-specified ChartSpec for use in tests."""
    return ChartSpec(
        question_ref=question_ref,
        chart_type=chart_type,
        statistic="pct",
        classifying_var=None,
        number_format=NumberFormat(pct_decimals=1, mean_decimals=2, count_round_up=True, show_pct_sign=False),
        sort=SortSpec(basis="pct", topbox_codes=(4.0, 5.0), descending=True),
        template_slot="slot-A",
        elements=ElementToggles(title=True, legend=False, n=True, axis_names=True, filter_var=False, data_labels=True),
        scatter_xy=None,
    )


def _make_report(*question_refs: str) -> Report:
    """Build a Report with one ChartSpec per question_ref supplied."""
    charts = tuple(_make_chart(qr) for qr in question_refs)
    return Report(
        name="Test Report",
        render_mode="native",
        template_ref="template-001",
        charts=charts,
    )


def _report_body(report: Report) -> dict:
    """Serialize a Report to the dict that the POST/PUT endpoints accept as a body."""
    return json.loads(report_to_json(report))


def _make_client() -> Mock:
    """Return a fresh Mock that stands in for DataHiveClient."""
    return Mock()


# ---------------------------------------------------------------------------
# Test 1 — Create → load round-trip: exact charts, arbitrary count
# REQ-C-08, REQ-C-10, REQ-C-11
# ---------------------------------------------------------------------------


def test_create_and_load_exact_round_trip() -> None:
    """POST a 3-chart report; capture the JSON saved to the store; GET it back and assert the
    round-trip is exact: report_from_json(GET body) == report_from_json(original). Also asserts
    the chart count survives. (REQ-C-08, REQ-C-10, REQ-C-11)"""
    mock = _make_client()
    mock.save_report.return_value = "rep-1"

    app = create_app(client=mock)
    client = TestClient(app)

    original = _make_report("q1", "q2", "q3")
    body = _report_body(original)

    # POST to create
    resp = client.post("/cases/case-42/reports", json=body)
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["report_id"] == "rep-1"

    # Capture the exact JSON that was passed to save_report
    call_args = mock.save_report.call_args
    # positional: (case_id, report_id, report_json, readable)
    captured_json: str = call_args[0][2]  # 3rd positional argument

    # Feed captured JSON back through load_report and GET
    mock.load_report.return_value = captured_json
    resp_get = client.get("/cases/case-42/reports/rep-1")
    assert resp_get.status_code == 200

    # Exact round-trip: the parsed response reconstructs identically to the original
    loaded = report_from_json(resp_get.json())
    assert loaded == original  # Report is a frozen dataclass so == compares all fields/charts
    assert len(loaded.charts) == 3


# ---------------------------------------------------------------------------
# Test 2 — Duplicate yields a new id, id=None, new name baked in
# REQ-C-09
# ---------------------------------------------------------------------------


def test_duplicate_new_id_null_report_id_new_name_baked_in() -> None:
    """POST .../duplicate creates a new doc (save_report called with report_id=None), assigns the
    new name, and returns a new report_id. The saved JSON must contain the new name.
    (REQ-C-09)"""
    mock = _make_client()
    src = _make_report("q1", "q2")
    mock.load_report.return_value = report_to_json(src)
    mock.save_report.return_value = "rep-2"

    app = create_app(client=mock)
    client = TestClient(app)

    resp = client.post("/cases/case-42/reports/rep-1/duplicate", json={"name": "Copy"})
    assert resp.status_code in (200, 201), resp.text
    assert resp.json()["report_id"] == "rep-2"

    # save_report must have been called with report_id=None (2nd positional arg)
    call_args = mock.save_report.call_args
    assert call_args[0][1] is None, "report_id arg to save_report must be None for a new doc"

    # The saved JSON must contain the new name
    saved_json: str = call_args[0][2]
    assert "Copy" in saved_json
    assert report_from_json(saved_json).name == "Copy"


# ---------------------------------------------------------------------------
# Test 3 — PUT versioned save passes the existing report_id
# REQ-C-08
# ---------------------------------------------------------------------------


def test_put_versioned_save_passes_report_id() -> None:
    """PUT /cases/{case_id}/reports/{report_id} calls save_report with the given report_id (not
    None), enabling versioned replace. (REQ-C-08)"""
    mock = _make_client()
    mock.save_report.return_value = "rep-99"

    app = create_app(client=mock)
    client = TestClient(app)

    report = _make_report("qA")
    body = _report_body(report)

    resp = client.put("/cases/case-42/reports/rep-99", json=body)
    assert resp.status_code == 200, resp.text
    assert resp.json()["report_id"] == "rep-99"

    call_args = mock.save_report.call_args
    assert call_args[0][1] == "rep-99", "save_report must receive the existing report_id for versioned save"


# ---------------------------------------------------------------------------
# Test 4 — DELETE calls delete_report and returns 2xx
# REQ-C-12
# ---------------------------------------------------------------------------


def test_delete_report_calls_delete_and_returns_2xx() -> None:
    """DELETE /cases/{case_id}/reports/{report_id} calls client.delete_report with the given id
    and returns a 2xx response. (REQ-C-12)"""
    mock = _make_client()
    mock.delete_report.return_value = None

    app = create_app(client=mock)
    client = TestClient(app)

    resp = client.delete("/cases/case-42/reports/rep-del")
    assert resp.status_code in (200, 204), resp.text
    mock.delete_report.assert_called_once_with("rep-del")
