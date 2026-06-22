"""Tests for cases routes: POST /cases (create) and GET /cases (list). (REQ-C-03, REQ-C-07)"""
from unittest.mock import Mock

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app


def test_post_cases_creates_case_and_returns_case_id() -> None:
    """POST /cases with {"name": "Acme tracker"} returns 200/201 and body with case_id. (REQ-C-03)"""
    mock_client = Mock()
    mock_client.create_case.return_value = "case-123"

    app = create_app(client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/cases", json={"name": "Acme tracker"})

    assert response.status_code in (200, 201)
    assert response.json()["case_id"] == "case-123"
    mock_client.create_case.assert_called_once_with("Acme tracker")


def test_get_cases_lists_cases() -> None:
    """GET /cases returns 200 and the list of cases with id and name fields. (REQ-C-07)"""
    mock_client = Mock()
    mock_client.list_cases.return_value = [
        {"id": "c1", "name": "A"},
        {"id": "c2", "name": "B"},
    ]

    app = create_app(client=mock_client)
    test_client = TestClient(app)

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


def test_post_cases_with_missing_name_returns_422() -> None:
    """POST /cases with missing/empty name returns 422 validation error. (REQ-C-03)"""
    mock_client = Mock()
    app = create_app(client=mock_client)
    test_client = TestClient(app)

    response = test_client.post("/cases", json={})

    assert response.status_code == 422
