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
    assert len(body["questions"]) == 1
    q = body["questions"][0]
    # Check the core fields (W1 adds suggested_chart_type + missing_values; allow those)
    assert q["qid"] == "v1"
    assert q["kind"] == "single"
    assert q["variables"] == ["v1"]
    assert q["text"] == "Satisfaction"


def test_get_questions_includes_values_and_category_labels(tmp_path) -> None:
    """questions response includes `values` (all value labels incl. missing) and
    `category_labels` (non-missing labels in render order). (Task B)"""
    model = QuestionModel(
        variables={
            "v1": Variable(
                name="v1",
                label="Satisfaction",
                measurement="categorical",
                value_labels=(
                    ValueLabel(1.0, "Low"),
                    ValueLabel(2.0, "High"),
                    ValueLabel(99.0, "EOS"),
                ),
                missing_values=frozenset({99.0}),
            )
        },
        questions=[Question(qid="v1", kind="single", variables=("v1",), text="Satisfaction")],
    )
    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)
    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = client.get("/materials/mat-3/questions")
    assert response.status_code == 200
    q = response.json()["questions"][0]
    # values includes the missing code so the picker can show/uncheck it
    assert q["values"] == [
        {"code": 1.0, "label": "Low"},
        {"code": 2.0, "label": "High"},
        {"code": 99.0, "label": "EOS"},
    ]
    # category_labels excludes the missing code
    assert q["category_labels"] == ["Low", "High"]
    # missing_values still present (SAV-detected default)
    assert q["missing_values"] == [{"code": 99.0, "label": "EOS"}]


def test_get_questions_multi_values_empty(tmp_path) -> None:
    """Multi questions return `values` == [] and member labels as category_labels. (Task B)"""
    model = _make_grouped_model()
    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)
    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = client.get("/materials/mat-4/questions")
    assert response.status_code == 200
    multi = [q for q in response.json()["questions"] if q["kind"] == "multi"]
    assert multi, "expected an auto-grouped multi question"
    assert multi[0]["values"] == []
    assert multi[0]["category_labels"] == ["Brand A awareness", "Brand B awareness"]


def test_chart_spec_body_maps_new_option_fields() -> None:
    """preview-chart body fields map onto the ChartSpec (incl. None-vs-tuple). (Task B)"""
    from reportbuilder.api.routes_questions import ChartSpecBody, _chart_spec_from_body

    body = ChartSpecBody(
        question_ref="q1",
        chart_type="horizontal_bar",
        show_empty_categories=False,
        not_answered_codes=[99.0],
        category_label_overrides=[["Poor", "P"], ["Good", "G"]],
    )
    spec = _chart_spec_from_body(body)
    assert spec.show_empty_categories is False
    assert spec.not_answered_codes == (99.0,)
    assert spec.category_label_overrides == (("Poor", "P"), ("Good", "G"))

    # None stays None (distinct from empty tuple); defaults stay backward-compatible.
    default_spec = _chart_spec_from_body(
        ChartSpecBody(question_ref="q1", chart_type="horizontal_bar"))
    assert default_spec.not_answered_codes is None
    assert default_spec.show_empty_categories is True
    assert default_spec.category_label_overrides == ()


# ---------------------------------------------------------------------------
# Task G.1 / G.2: chartable flag + compatible_chart_types
# ---------------------------------------------------------------------------


def _text_question_model() -> QuestionModel:
    """A single open-ended text question plus a normal categorical one."""
    variables = {
        "other": Variable(
            name="other",
            label="Muut hoivapalvelut, mitkä?",
            measurement="text",
            value_labels=(),
            missing_values=frozenset(),
        ),
        "sat": Variable(
            name="sat",
            label="Satisfaction",
            measurement="categorical",
            value_labels=(ValueLabel(1.0, "Low"), ValueLabel(2.0, "High")),
            missing_values=frozenset(),
        ),
    }
    questions = [
        Question(qid="other", kind="single", variables=("other",), text="Muut hoivapalvelut, mitkä?"),
        Question(qid="sat", kind="single", variables=("sat",), text="Satisfaction"),
    ]
    return QuestionModel(variables=variables, questions=questions)


def _get_questions(model):
    mock_client = Mock()
    app = create_app(client=mock_client)
    client = TestClient(app)
    with patch("reportbuilder.api.routes_questions.load_model_for_material") as mock_load:
        mock_load.return_value = model
        response = client.get("/materials/mat-G/questions")
    assert response.status_code == 200
    return response.json()["questions"]


def test_text_question_is_chartable_as_wordcloud():
    """An open-ended text question is chartable — defaulting to AI-summarised
    "themes" with the word cloud still available; a normal categorical question
    stays chartable and never offers themes/wordcloud."""
    qs = {q["qid"]: q for q in _get_questions(_text_question_model())}
    assert qs["other"]["chartable"] is True
    assert qs["other"]["non_chartable_reason"] is None
    assert qs["other"]["compatible_chart_types"] == ["themes", "wordcloud"]
    assert qs["other"]["suggested_chart_type"] == "themes"

    assert qs["sat"]["chartable"] is True
    assert qs["sat"]["non_chartable_reason"] is None
    assert qs["sat"]["compatible_chart_types"]  # non-empty
    # A non-text question must NOT offer the word cloud.
    assert "wordcloud" not in qs["sat"]["compatible_chart_types"]
    assert qs["sat"]["suggested_chart_type"] != "wordcloud"


def test_compatible_chart_types_multi_offers_pie_but_suggests_bar():
    """A multi-response question is a single series, so pie/doughnut ARE offered
    (the user may legitimately want a pie when the option shares read as parts of
    a whole, e.g. a "pick one if you have several" question summing to ~100%).
    The smart DEFAULT for multi stays horizontal_bar — pie is available, not
    auto-suggested."""
    qs = _get_questions(_make_grouped_model())
    multi = [q for q in qs if q["kind"] == "multi"]
    assert multi, "expected an auto-grouped multi question"
    compatible = multi[0]["compatible_chart_types"]
    assert "pie" in compatible
    assert "doughnut" in compatible
    assert "horizontal_bar" in compatible
    assert multi[0]["suggested_chart_type"] == "horizontal_bar"


# ---------------------------------------------------------------------------
# PUT /materials/{material_id}/grouping — multi  (REQ-C-06, M-02)
# ---------------------------------------------------------------------------


def test_regroup_combines_returns_reshaped_questions(tmp_path) -> None:
    """POST /regroup returns the reshaped (stateless) question list with the group.
    (REQ-C-06, M-02) — the full contract is covered in the suite."""
    singles = _make_singles_model()
    tc = TestClient(create_app(client=Mock()))
    with patch("reportbuilder.api.routes_questions._load_singles", return_value=singles):
        response = tc.post(
            "/materials/mat-1/regroup",
            json={"groups": [{"kind": "multi", "variables": ["q1_1", "q1_2"]}], "singles": []},
        )
    assert response.status_code == 200
    qs = response.json()["questions"]
    assert any(q["kind"] == "multi" and set(q["variables"]) == {"q1_1", "q1_2"} for q in qs)


def test_regroup_invalid_groups_are_ignored(tmp_path) -> None:
    """Regroup is lenient — an invalid group (scale member, or too few variables)
    is silently skipped, still returning 200. (REQ-C-06)"""
    singles = _make_singles_model()
    tc = TestClient(create_app(client=Mock()))
    with patch("reportbuilder.api.routes_questions._load_singles", return_value=singles):
        scale = tc.post("/materials/mat-1/regroup",
                        json={"groups": [{"kind": "multi", "variables": ["q1_1", "age"]}]})
        too_few = tc.post("/materials/mat-1/regroup",
                          json={"groups": [{"kind": "multi", "variables": ["q1_1"]}]})
    assert scale.status_code == 200
    assert too_few.status_code == 200


