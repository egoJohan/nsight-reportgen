"""Tests for materials routes: POST /cases/{case_id}/materials (upload SAV + ingest). (REQ-C-01, REQ-C-04)"""
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel


def test_upload_material_successful_upload() -> None:
    """POST /cases/{case_id}/materials successfully uploads SAV, ingests it, and attaches under case.
    (REQ-C-01, REQ-C-04)
    """
    # Create a fake QuestionModel with 3 questions
    fake_model = QuestionModel(
        variables={
            "q1_var": Variable(
                name="q1_var",
                label="Question 1",
                measurement="categorical",
                value_labels=(ValueLabel(1, "Yes"), ValueLabel(0, "No")),
                missing_values=frozenset(),
            ),
            "q2_var": Variable(
                name="q2_var",
                label="Question 2",
                measurement="categorical",
                value_labels=(),
                missing_values=frozenset(),
            ),
            "q3_var": Variable(
                name="q3_var",
                label="Question 3",
                measurement="scale",
                value_labels=(),
                missing_values=frozenset(),
            ),
        },
        questions=[
            Question(qid="q1", kind="single", variables=("q1_var",), text="Question 1"),
            Question(qid="q2", kind="single", variables=("q2_var",), text="Question 2"),
            Question(qid="q3", kind="single", variables=("q3_var",), text="Question 3"),
        ],
    )

    mock_client = Mock()
    mock_client.attach_material.return_value = "mat-9"

    app = create_app(client=mock_client)
    test_client = TestClient(app)

    test_bytes = b"fake-sav-file-bytes"

    with patch("reportbuilder.api.routes_materials.read_sav") as mock_read_sav:
        mock_read_sav.return_value = (None, fake_model)  # df not needed for this test

        response = test_client.post(
            "/cases/case-1/materials",
            files={"file": ("survey.sav", test_bytes, "application/octet-stream")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["material_id"] == "mat-9"
    assert body["question_count"] == 3

    # Verify client.attach_material was called once
    mock_client.attach_material.assert_called_once()
    call_args = mock_client.attach_material.call_args
    # Check positional arguments: (case_id, name, sav_bytes, codebook_summary)
    assert call_args[0][0] == "case-1"  # case_id
    assert call_args[0][1] == "survey.sav"  # name
    assert call_args[0][2] == test_bytes  # sav_bytes (the uploaded bytes)
    # codebook_summary is the 4th arg; validate it contains expected parts
    codebook = call_args[0][3]
    assert "3 questions, 3 variables" in codebook
    assert "q1\tsingle\tQuestion 1" in codebook
    assert "q2\tsingle\tQuestion 2" in codebook
    assert "q3\tsingle\tQuestion 3" in codebook


def test_upload_material_read_sav_is_invoked() -> None:
    """POST /cases/{case_id}/materials invokes read_sav on the uploaded bytes. (REQ-C-01)"""
    fake_model = QuestionModel(
        variables={},
        questions=[
            Question(qid="q1", kind="single", variables=("var",), text="Q1"),
        ],
    )

    mock_client = Mock()
    mock_client.attach_material.return_value = "mat-x"

    app = create_app(client=mock_client)
    test_client = TestClient(app)

    test_bytes = b"another-sav-bytes"

    with patch("reportbuilder.api.routes_materials.read_sav") as mock_read_sav:
        mock_read_sav.return_value = (None, fake_model)

        response = test_client.post(
            "/cases/case-2/materials",
            files={"file": ("data.sav", test_bytes, "application/octet-stream")},
        )

    assert response.status_code == 200
    # Verify read_sav was called exactly once
    mock_read_sav.assert_called_once()
    # Verify the temp file path was passed (we can't check the exact path, but it should be a string)
    call_args = mock_read_sav.call_args
    assert isinstance(call_args[0][0], str)
