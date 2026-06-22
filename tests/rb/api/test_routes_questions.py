"""Tests for questions routes: GET /materials/{material_id}/questions,
PUT /materials/{material_id}/grouping. (REQ-C-05, REQ-C-06, M-02)"""
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel


def _make_singles_model() -> QuestionModel:
    """Build a minimal QuestionModel with two single questions (q1_1, q1_2) that share a prefix,
    both binary — eligible for multi-grouping — plus one unrelated single (age)."""
    variables = {
        "q1_1": Variable(
            name="q1_1",
            label="Brand A awareness",
            measurement="categorical",
            value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
            missing_values=frozenset(),
        ),
        "q1_2": Variable(
            name="q1_2",
            label="Brand B awareness",
            measurement="categorical",
            value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
            missing_values=frozenset(),
        ),
        "age": Variable(
            name="age",
            label="Age",
            measurement="scale",
            value_labels=(),
            missing_values=frozenset(),
        ),
    }
    questions = [
        Question(qid="q1-1", kind="single", variables=("q1_1",), text="Brand A awareness"),
        Question(qid="q1-2", kind="single", variables=("q1_2",), text="Brand B awareness"),
        Question(qid="age", kind="single", variables=("age",), text="Age"),
    ]
    return QuestionModel(variables=variables, questions=questions)


def _make_grouped_model() -> QuestionModel:
    """QuestionModel with auto-detected multi group applied to q1_1+q1_2."""
    from reportbuilder.ingest.multi_group import suggest_multi_groups, apply_groups

    singles = _make_singles_model()
    groups = suggest_multi_groups(singles)
    if groups:
        return apply_groups(singles, groups)
    return singles


# ---------------------------------------------------------------------------
# GET /materials/{material_id}/questions  (REQ-C-05)
# ---------------------------------------------------------------------------


def test_get_questions_returns_list(tmp_path) -> None:
    """GET /materials/{material_id}/questions returns 200 and a list of question dicts.
    (REQ-C-05)"""
    grouped_model = _make_grouped_model()

    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = grouped_model
        response = client.get("/materials/mat-1/questions")

    assert response.status_code == 200
    body = response.json()
    questions = body["questions"]
    assert len(questions) >= 1
    # Every entry has the required fields
    for q in questions:
        assert "qid" in q
        assert "kind" in q
        assert "variables" in q
        assert "text" in q
    # load_model_for_material was called with the material_id and the client
    mock_load.assert_called_once()
    call_args = mock_load.call_args
    assert call_args[0][0] == "mat-1"


def test_get_questions_field_values(tmp_path) -> None:
    """GET /materials/{material_id}/questions returns correct field values. (REQ-C-05)"""
    # Use a simple single question model for easy assertion
    simple_model = QuestionModel(
        variables={
            "v1": Variable(
                name="v1",
                label="Satisfaction",
                measurement="categorical",
                value_labels=(ValueLabel(1.0, "Low"), ValueLabel(5.0, "High")),
                missing_values=frozenset(),
            )
        },
        questions=[
            Question(qid="v1", kind="single", variables=("v1",), text="Satisfaction"),
        ],
    )

    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)

    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = simple_model
        response = client.get("/materials/mat-2/questions")

    assert response.status_code == 200
    body = response.json()
    assert body["questions"] == [
        {"qid": "v1", "kind": "single", "variables": ["v1"], "text": "Satisfaction"}
    ]


# ---------------------------------------------------------------------------
# PUT /materials/{material_id}/grouping — multi  (REQ-C-06, M-02)
# ---------------------------------------------------------------------------


def test_put_grouping_multi_returns_multi_question(tmp_path) -> None:
    """PUT /materials/{material_id}/grouping with kind=multi returns a multi question containing
    both variables. Stateless preview — no persistence. (REQ-C-06, M-02)"""
    singles = _make_singles_model()

    mock_client = Mock()
    app = create_app(client=mock_client)
    tc = TestClient(app)

    # Patch _load_singles so we get a controllable singles model without real .sav I/O
    with patch("reportbuilder.api.routes_questions._load_singles") as mock_singles:
        mock_singles.return_value = singles
        response = tc.put(
            "/materials/mat-1/grouping",
            json={"variables": ["q1_1", "q1_2"], "kind": "multi"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "multi"
    assert "q1_1" in body["variables"]
    assert "q1_2" in body["variables"]


# ---------------------------------------------------------------------------
# PUT /materials/{material_id}/grouping — single  (REQ-C-06)
# ---------------------------------------------------------------------------


def test_put_grouping_single_returns_single_questions(tmp_path) -> None:
    """PUT /materials/{material_id}/grouping with kind=single returns single question entries for
    each supplied variable. Stateless preview — no persistence. (REQ-C-06)"""
    singles = _make_singles_model()

    mock_client = Mock()
    app = create_app(client=mock_client)
    tc = TestClient(app)

    with patch("reportbuilder.api.routes_questions._load_singles") as mock_singles:
        mock_singles.return_value = singles
        response = tc.put(
            "/materials/mat-1/grouping",
            json={"variables": ["q1_1"], "kind": "single"},
        )

    assert response.status_code == 200
    body = response.json()
    # The response is a list of single question dicts
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["kind"] == "single"
    assert body[0]["variables"] == ["q1_1"]
