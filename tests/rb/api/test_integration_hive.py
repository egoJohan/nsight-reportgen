"""Live-hive integration test: full REST round-trip against a real datahive.
(Phase 7, Task 7.7 — INTEG, skipped unless NSIGHT_TEST_HIVE_URL env var is set.)
(REQ-C-03, REQ-C-04, REQ-C-07, REQ-C-08, D3)
"""
import os
import json
import pytest
from pathlib import Path

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.store.datahive_client import DataHiveClient
from reportbuilder.model.report import (
    Report, ChartSpec, SortSpec, NumberFormat, ElementToggles,
    report_to_json, report_from_json,
)
from reportbuilder.testing.fixtures import synthetic_sav

# Module-level skip guard: skip all tests unless NSIGHT_TEST_HIVE_URL is set
HIVE_URL = os.environ.get("NSIGHT_TEST_HIVE_URL")
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not HIVE_URL, reason="set NSIGHT_TEST_HIVE_URL to run"),
]


@pytest.fixture
def hive_client():
    """Fixture: build a DataHiveClient pointed at the real hive (skipped by pytest.mark.skipif
    at module level, so this never runs in the default suite)."""
    token = os.environ.get("NSIGHT_TEST_HIVE_TOKEN")
    return DataHiveClient(base_url=HIVE_URL, token=token)


@pytest.fixture
def test_client(hive_client):
    """Fixture: build the FastAPI app with the real hive client, wrapped in TestClient."""
    app = create_app(client=hive_client)
    return TestClient(app)


@pytest.fixture
def synthetic_sav_file(tmp_path):
    """Fixture: generate a tiny synthetic .sav file for multipart upload."""
    return synthetic_sav(tmp_path)


def test_full_round_trip_against_live_hive(test_client, synthetic_sav_file):
    """End-to-end REST flow against live hive:
    1. POST /cases → create case, capture case_id (REQ-C-03/07)
    2. POST /cases/{case_id}/materials → upload .sav, assert question_count >= 1 (REQ-C-04)
    3. GET /cases → assert created case appears (REQ-C-07)
    4. POST /cases/{case_id}/reports → create minimal report (REQ-C-08)
    5. GET /cases/{case_id}/reports/{report_id} → assert exact JSON round-trip (D3, REQ-C-08)
    """
    # Step 1: Create a case
    resp_create_case = test_client.post(
        "/cases",
        json={"name": "INTEG test-live-hive"},
    )
    assert resp_create_case.status_code in (200, 201), resp_create_case.text
    case_data = resp_create_case.json()
    case_id = case_data["case_id"]
    assert case_id is not None

    # Step 2: Upload a synthetic .sav material
    with open(synthetic_sav_file, "rb") as f:
        sav_bytes = f.read()

    resp_upload = test_client.post(
        f"/cases/{case_id}/materials",
        files={"file": ("synthetic.sav", sav_bytes, "application/octet-stream")},
    )
    assert resp_upload.status_code == 200, resp_upload.text
    material_data = resp_upload.json()
    material_id = material_data["material_id"]
    question_count = material_data["question_count"]
    assert material_id is not None
    assert question_count >= 1, "Synthetic SAV should have at least 1 question"

    # Step 3: List cases and verify the created case appears
    resp_list_cases = test_client.get("/cases")
    assert resp_list_cases.status_code == 200, resp_list_cases.text
    cases_data = resp_list_cases.json()
    # Response can be a dict with "cases" key or a raw list
    if isinstance(cases_data, dict):
        cases = cases_data.get("cases", [])
    else:
        cases = cases_data
    # Find the created case in the list
    created_case = None
    for case in cases:
        if case.get("id") == case_id:
            created_case = case
            break
    assert created_case is not None, f"Created case {case_id} not found in list"
    assert created_case.get("name") == "INTEG test-live-hive"

    # Step 4: Create a report with one chart referencing a question from the material
    # Use the first question id we expect from synthetic_sav (q1 or age, etc.)
    # The synthetic_sav fixture has "q1" as the first question
    minimal_report = Report(
        name="INTEG Test Report",
        render_mode="native",
        template_ref="template-001",
        charts=(
            ChartSpec(
                question_ref="q1",  # First question in synthetic_sav
                chart_type="vertical_bar",
                statistic="pct",
                classifying_var=None,
                number_format=NumberFormat(),
                sort=SortSpec(basis="data_order"),
                template_slot="slot-1",
                elements=ElementToggles(),
            ),
        ),
    )
    original_report_json = report_to_json(minimal_report)
    original_report_dict = json.loads(original_report_json)

    resp_create_report = test_client.post(
        f"/cases/{case_id}/reports",
        json=original_report_dict,
    )
    assert resp_create_report.status_code in (200, 201), resp_create_report.text
    report_data = resp_create_report.json()
    report_id = report_data["report_id"]
    assert report_id is not None

    # Step 5: Fetch the report and verify exact JSON round-trip (D3)
    resp_fetch_report = test_client.get(f"/cases/{case_id}/reports/{report_id}")
    assert resp_fetch_report.status_code == 200, resp_fetch_report.text
    fetched_report_dict = resp_fetch_report.json()

    # Parse both through report_from_json to normalize and compare
    original_parsed = report_from_json(original_report_dict)
    fetched_parsed = report_from_json(fetched_report_dict)

    # Exact round-trip: reports should be equal
    assert fetched_parsed == original_parsed, (
        f"Report round-trip failed.\n"
        f"Original: {original_parsed}\n"
        f"Fetched: {fetched_parsed}"
    )
