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


def test_post_cases_is_gone_and_names_its_replacement(rb_wire) -> None:
    """POST /cases refuses with 410 and points at the route that works.

    A study belongs to a customer, and this pre-hierarchy route carries none in
    its path, so it cannot succeed — RepositoryClient has no create_case at all.
    It used to 500 on an AttributeError; it now says plainly that it is gone and
    where to go instead. The replacement is POST /customers/{id}/cases."""
    test_client = rb_wire(client=Mock())

    response = test_client.post("/cases", json={"name": "Acme tracker"})

    assert response.status_code == 410
    assert "/customers/" in response.json()["detail"]


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


def test_post_cases_is_gone_whatever_the_body(rb_wire) -> None:
    """410 before validation: the route is gone, so the body is beside the point.

    It used to answer 422 for a missing name, which implied that a well-formed
    body would have worked. None will."""
    test_client = rb_wire(client=Mock())

    assert test_client.post("/cases", json={}).status_code == 410
