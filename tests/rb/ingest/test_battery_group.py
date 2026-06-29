"""Battery grouping — a 2D rating grid (`<category>:<subject>:<question>`) is
collapsed into one battery question per subject, with the categories as members.
Generic: not tied to brand-image specifically."""
from __future__ import annotations

from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel
from reportbuilder.ingest.battery_group import suggest_batteries, apply_batteries


def _rating(name: str, label: str) -> Variable:
    # 1-5 rating with the quirky encoding seen in the real data.
    return Variable(
        name=name, label=label, measurement="categorical",
        value_labels=(
            ValueLabel(2.0, "2"), ValueLabel(3.0, "3"), ValueLabel(4.0, "4"),
            ValueLabel(10070.0, "1 - Ei vastaa lainkaan"),
            ValueLabel(10074.0, "5 - Vastaa erittäin hyvin"),
            ValueLabel(10075.0, "En osaa sanoa"),
        ),
        missing_values=frozenset(),
    )


def _grid_model() -> QuestionModel:
    """2 subjects (Attendo, Esperi) × 3 attributes, plus one unrelated single."""
    q = "Arvioi mielikuvaasi. Vastaa asteikolla 1-5"
    cells = {}
    n = 0
    for subj in ("Attendo", "Esperi"):
        for attr in ("Luotettava", "Inhimillinen", "Ahne"):
            n += 1
            cells[f"v{n}"] = _rating(f"v{n}", f"{attr}:{subj}: {q}")
    cells["age"] = Variable("age", "Ikä", "scale", (), frozenset())
    questions = [
        Question(qid=k, kind="single", variables=(k,), text=cells[k].label)
        for k in cells
    ]
    return QuestionModel(variables=cells, questions=questions)


def test_suggest_finds_one_battery_per_subject():
    batteries = suggest_batteries(_grid_model(), min_members=2)
    subjects = sorted(b[0] for b in batteries)
    assert subjects == ["Attendo", "Esperi"]
    for _subj, members in batteries:
        assert len(members) == 3  # the three attributes


def test_apply_creates_battery_questions_and_consumes_cells():
    model = _grid_model()
    batteries = suggest_batteries(model, min_members=2)
    grouped = apply_batteries(model, batteries)

    batt = [q for q in grouped.questions if q.kind == "battery"]
    assert len(batt) == 2
    # The 6 grid cells are no longer standalone single questions.
    singles = [q for q in grouped.questions if q.kind == "single"]
    assert {q.qid for q in singles} == {"age"}

    # Member labels are rewritten to the attribute (category), no colon.
    one = next(q for q in batt if "Attendo" in q.text)
    cats = [grouped.variables[v].label for v in one.variables]
    assert set(cats) == {"Luotettava", "Inhimillinen", "Ahne"}
    assert all(":" not in c for c in cats)


def test_no_grid_no_batteries():
    """A model without the 2-colon grid pattern yields no batteries."""
    v = {"a": Variable("a", "Plain question", "categorical", (), frozenset())}
    m = QuestionModel(variables=v, questions=[Question(qid="a", kind="single", variables=("a",), text="Plain question")])
    assert suggest_batteries(m) == []
