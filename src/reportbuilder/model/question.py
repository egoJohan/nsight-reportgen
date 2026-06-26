"""Question Model — the normalized survey contract (design §6)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class ValueLabel:
    value: float
    label: str


@dataclass(frozen=True)
class Variable:
    name: str                              # SPSS variable name
    label: str                             # variable label -> question text (REQ-D-04)
    measurement: str                       # "categorical" | "scale"
    value_labels: tuple[ValueLabel, ...]   # (REQ-D-05)
    missing_values: frozenset[float]       # user-defined missing; Sysmis=NaN handled separately (REQ-D-06, MV-02)


@dataclass(frozen=True)
class Question:
    qid: str                               # stable id (slug of primary variable / group)
    kind: str                              # "single" | "multi" (REQ-C-06, M-01/02)
    variables: tuple[str, ...]             # 1 for single; N for multi group
    text: str                              # question text from the variable label


@dataclass
class QuestionModel:
    variables: dict[str, Variable]         # name -> Variable
    questions: list[Question]

    def question(self, qid: str) -> Question:
        for q in self.questions:
            if q.qid == qid:
                return q
        raise KeyError(qid)

    def variable(self, name: str) -> Variable:
        return self.variables[name]

    def missing_value_labels(self, qid: str) -> list[tuple[float, str]]:
        """Return (code, label) pairs for user-missing values of the primary variable.

        Sorted by code ascending. Falls back to the bare code as a string when the
        variable has no label entry for that missing code. (REQ-D-06)
        """
        q = self.question(qid)
        var = self.variables[q.variables[0]]
        label_map = {vl.value: vl.label for vl in var.value_labels}
        return [
            (code, label_map.get(code, str(int(code) if code == int(code) else code)))
            for code in sorted(var.missing_values)
        ]
