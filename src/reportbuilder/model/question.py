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
