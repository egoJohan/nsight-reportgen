"""Tests for the Question Model — the normalized survey contract."""

import dataclasses
import pytest

from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel


class TestValueLabel:
    """Test ValueLabel frozen dataclass."""

    def test_value_label_creation(self):
        """Verify ValueLabel can be created with value and label."""
        vl = ValueLabel(value=1.0, label="Strongly agree")
        assert vl.value == 1.0
        assert vl.label == "Strongly agree"

    def test_value_label_frozen(self):
        """Verify ValueLabel is frozen (immutable)."""
        vl = ValueLabel(value=1.0, label="Strongly agree")
        with pytest.raises(dataclasses.FrozenInstanceError):
            vl.value = 2.0
        with pytest.raises(dataclasses.FrozenInstanceError):
            vl.label = "Disagree"


class TestVariable:
    """Test Variable frozen dataclass."""

    def test_variable_creation(self):
        """Verify Variable can be created with all required fields."""
        vls = (ValueLabel(1.0, "Yes"), ValueLabel(0.0, "No"))
        var = Variable(
            name="Q1",
            label="Do you agree?",
            measurement="categorical",
            value_labels=vls,
            missing_values=frozenset([999.0])
        )
        assert var.name == "Q1"
        assert var.label == "Do you agree?"
        assert var.measurement == "categorical"
        assert var.value_labels == vls
        assert var.missing_values == frozenset([999.0])

    def test_variable_frozen(self):
        """Verify Variable is frozen (immutable)."""
        vls = (ValueLabel(1.0, "Yes"), ValueLabel(0.0, "No"))
        var = Variable(
            name="Q1",
            label="Do you agree?",
            measurement="categorical",
            value_labels=vls,
            missing_values=frozenset([999.0])
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            var.name = "Q2"
        with pytest.raises(dataclasses.FrozenInstanceError):
            var.label = "Different label"
        with pytest.raises(dataclasses.FrozenInstanceError):
            var.measurement = "scale"

    def test_variable_with_empty_missing_values(self):
        """Verify Variable can be created with empty missing_values."""
        vls = (ValueLabel(1.0, "Yes"),)
        var = Variable(
            name="Q1",
            label="Do you agree?",
            measurement="scale",
            value_labels=vls,
            missing_values=frozenset()
        )
        assert var.missing_values == frozenset()

    def test_variable_with_empty_value_labels(self):
        """Verify Variable can be created with empty value_labels."""
        var = Variable(
            name="Q1",
            label="Rate on scale",
            measurement="scale",
            value_labels=tuple(),
            missing_values=frozenset([999.0])
        )
        assert var.value_labels == tuple()


class TestQuestion:
    """Test Question frozen dataclass."""

    def test_question_single_creation(self):
        """Verify Question can be created for a single-response question."""
        q = Question(
            qid="q1",
            kind="single",
            variables=("Q1",),
            text="Do you agree?"
        )
        assert q.qid == "q1"
        assert q.kind == "single"
        assert q.variables == ("Q1",)
        assert q.text == "Do you agree?"

    def test_question_multi_creation(self):
        """Verify Question can be created for a multi-response question."""
        q = Question(
            qid="q2",
            kind="multi",
            variables=("Q2_1", "Q2_2", "Q2_3"),
            text="Select all that apply"
        )
        assert q.qid == "q2"
        assert q.kind == "multi"
        assert q.variables == ("Q2_1", "Q2_2", "Q2_3")
        assert q.text == "Select all that apply"

    def test_question_frozen(self):
        """Verify Question is frozen (immutable)."""
        q = Question(
            qid="q1",
            kind="single",
            variables=("Q1",),
            text="Do you agree?"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            q.qid = "q2"
        with pytest.raises(dataclasses.FrozenInstanceError):
            q.kind = "multi"
        with pytest.raises(dataclasses.FrozenInstanceError):
            q.text = "Different text"


class TestQuestionModel:
    """Test QuestionModel mutable dataclass with lookup methods."""

    def test_question_model_creation(self):
        """Verify QuestionModel can be created with variables and questions."""
        vls = (ValueLabel(1.0, "Yes"), ValueLabel(0.0, "No"))
        var1 = Variable(
            name="Q1",
            label="Do you agree?",
            measurement="categorical",
            value_labels=vls,
            missing_values=frozenset()
        )
        q = Question(
            qid="q1",
            kind="single",
            variables=("Q1",),
            text="Do you agree?"
        )
        model = QuestionModel(
            variables={"Q1": var1},
            questions=[q]
        )
        assert "Q1" in model.variables
        assert len(model.questions) == 1

    def test_question_lookup(self):
        """Verify QuestionModel.question(qid) resolves questions by qid."""
        q1 = Question(qid="q1", kind="single", variables=("Q1",), text="Text 1")
        q2 = Question(qid="q2", kind="single", variables=("Q2",), text="Text 2")
        model = QuestionModel(variables={}, questions=[q1, q2])

        assert model.question("q1") == q1
        assert model.question("q2") == q2

    def test_question_lookup_missing_raises_key_error(self):
        """Verify QuestionModel.question(qid) raises KeyError for missing qid."""
        q = Question(qid="q1", kind="single", variables=("Q1",), text="Text 1")
        model = QuestionModel(variables={}, questions=[q])

        with pytest.raises(KeyError):
            model.question("nonexistent")

    def test_variable_lookup(self):
        """Verify QuestionModel.variable(name) resolves variables by name."""
        var1 = Variable(
            name="Q1",
            label="Text 1",
            measurement="categorical",
            value_labels=tuple(),
            missing_values=frozenset()
        )
        var2 = Variable(
            name="Q2",
            label="Text 2",
            measurement="scale",
            value_labels=tuple(),
            missing_values=frozenset()
        )
        model = QuestionModel(
            variables={"Q1": var1, "Q2": var2},
            questions=[]
        )

        assert model.variable("Q1") == var1
        assert model.variable("Q2") == var2

    def test_variable_lookup_missing_raises_key_error(self):
        """Verify QuestionModel.variable(name) raises KeyError for missing name."""
        var = Variable(
            name="Q1",
            label="Text",
            measurement="categorical",
            value_labels=tuple(),
            missing_values=frozenset()
        )
        model = QuestionModel(variables={"Q1": var}, questions=[])

        with pytest.raises(KeyError):
            model.variable("nonexistent")

    def test_question_model_is_mutable(self):
        """Verify QuestionModel (not frozen) can be mutated."""
        q1 = Question(qid="q1", kind="single", variables=("Q1",), text="Text 1")
        model = QuestionModel(variables={}, questions=[q1])

        # Should be able to mutate the model's questions list
        q2 = Question(qid="q2", kind="single", variables=("Q2",), text="Text 2")
        model.questions.append(q2)
        assert len(model.questions) == 2

    def test_question_model_integration(self):
        """Integration test: create a complete QuestionModel with multiple questions and variables."""
        vls_yes_no = (ValueLabel(1.0, "Yes"), ValueLabel(0.0, "No"))
        var_q1 = Variable(
            name="Q1",
            label="Do you agree?",
            measurement="categorical",
            value_labels=vls_yes_no,
            missing_values=frozenset([999.0])
        )
        var_q2_1 = Variable(
            name="Q2_1",
            label="Option A",
            measurement="categorical",
            value_labels=vls_yes_no,
            missing_values=frozenset()
        )
        var_q2_2 = Variable(
            name="Q2_2",
            label="Option B",
            measurement="categorical",
            value_labels=vls_yes_no,
            missing_values=frozenset()
        )

        q1 = Question(qid="q1", kind="single", variables=("Q1",), text="Do you agree?")
        q2 = Question(qid="q2", kind="multi", variables=("Q2_1", "Q2_2"), text="Select all that apply")

        model = QuestionModel(
            variables={"Q1": var_q1, "Q2_1": var_q2_1, "Q2_2": var_q2_2},
            questions=[q1, q2]
        )

        # Verify lookups work
        assert model.question("q1") == q1
        assert model.question("q2") == q2
        assert model.variable("Q1") == var_q1
        assert model.variable("Q2_1") == var_q2_1
        assert model.variable("Q2_2") == var_q2_2
