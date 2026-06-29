"""Multi-response member labels are cleaned to the option only.

The survey platform exports each multi sub-option's variable label as
``"<option>:<shared question>"``. apply_groups should strip the shared question
suffix so the category labels are the actual options — not option+question.
"""
from __future__ import annotations

from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel
from reportbuilder.ingest.multi_group import apply_groups


def _binary(name: str, label: str) -> Variable:
    return Variable(
        name=name, label=label, measurement="categorical",
        value_labels=(ValueLabel(0.0, "No"), ValueLabel(1.0, "Yes")),
        missing_values=frozenset(),
    )


def _model() -> QuestionModel:
    q = "Onko sinulla kokemusta hoivapalveluista? Valitse kaikki sopivat"
    variables = {
        "var11O19": _binary("var11O19", f"Kyllä, asiakkaana:{q}"),
        "var11O20": _binary("var11O20", f"Kyllä, läheisenä:{q}"),
        "var11O21": _binary("var11O21", f"Ei kokemusta:{q}"),
    }
    questions = [
        Question(qid=n, kind="single", variables=(n,), text=variables[n].label)
        for n in variables
    ]
    return QuestionModel(variables=variables, questions=questions)


def test_member_labels_stripped_to_option():
    model = _model()
    grouped = apply_groups(model, [("var11O19", "var11O20", "var11O21")])

    # Member variable labels are now the OPTION only (no ":question" suffix).
    assert grouped.variables["var11O19"].label == "Kyllä, asiakkaana"
    assert grouped.variables["var11O20"].label == "Kyllä, läheisenä"
    assert grouped.variables["var11O21"].label == "Ei kokemusta"
    for v in grouped.variables.values():
        assert ":" not in v.label

    # The grouped question text is the shared question stem.
    multi = next(q for q in grouped.questions if q.kind == "multi")
    assert multi.text == "Onko sinulla kokemusta hoivapalveluista? Valitse kaikki sopivat"


def test_non_pattern_labels_unchanged():
    """When members don't share a ':question' suffix, labels are left as-is."""
    variables = {
        "aO1": _binary("aO1", "Brand A"),
        "aO2": _binary("aO2", "Brand B"),
    }
    questions = [
        Question(qid=n, kind="single", variables=(n,), text=variables[n].label)
        for n in variables
    ]
    model = QuestionModel(variables=variables, questions=questions)
    grouped = apply_groups(model, [("aO1", "aO2")])
    assert grouped.variables["aO1"].label == "Brand A"
    assert grouped.variables["aO2"].label == "Brand B"
