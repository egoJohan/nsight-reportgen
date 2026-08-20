"""Tests for cases routes: POST /cases (create) and GET /cases (list). (REQ-C-03, REQ-C-07)

POST /cases: superseded by POST /customers/{customer_id}/cases (`fix(cases):
POST /cases refuses honestly instead of 500ing`, 88a02f4, predates the route
guards this file's setup was updated for) — it now always answers 410 Gone.
`test_post_cases_creates_case_and_returns_case_id` and
`test_post_cases_with_missing_name_returns_422` assert the old 200/422
behaviour and are left failing rather than edited: their assertions, not their
setup, are what no longer holds — see task-4c-report.md.
"""
from unittest.mock import Mock


def test_post_cases_creates_case_and_returns_case_id(rb_wire) -> None:
    """POST /cases with {"name": "Acme tracker"} returns 200/201 and body with case_id. (REQ-C-03)"""
    mock_client = Mock()
    mock_client.create_case.return_value = "case-123"

    test_client = rb_wire(client=mock_client)

    response = test_client.post("/cases", json={"name": "Acme tracker"})

    assert response.status_code in (200, 201)
    assert response.json()["case_id"] == "case-123"
    mock_client.create_case.assert_called_once_with("Acme tracker")


def test_get_cases_lists_cases(rb_wire) -> None:
    """GET /cases returns 200 and the list of cases with id and name fields. (REQ-C-07)"""
    mock_client = Mock()
    mock_client.list_cases.return_value = [
        {"id": "c1", "name": "A"},
        {"id": "c2", "name": "B"},
    ]

    test_client = rb_wire(client=mock_client)

    response = test_client.get("/cases")

    assert response.status_code == 200
    data = response.json()
    # The response can be either {"cases": [...]} or a raw list
    if isinstance(data, dict):
        cases = data.get("cases", [])
    else:
        cases = data
    assert len(cases) == 2
    assert cases[0]["id"] == "c1"
    assert cases[0]["name"] == "A"
    assert cases[1]["id"] == "c2"
    assert cases[1]["name"] == "B"
    mock_client.list_cases.assert_called_once()


def test_post_cases_with_missing_name_returns_422(rb_wire) -> None:
    """POST /cases with missing/empty name returns 422 validation error. (REQ-C-03)"""
    mock_client = Mock()
    test_client = rb_wire(client=mock_client)

    response = test_client.post("/cases", json={})

    assert response.status_code == 422
