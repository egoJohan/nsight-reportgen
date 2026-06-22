from __future__ import annotations
import os
import re
from collections import OrderedDict
from reportbuilder.model.question import QuestionModel, Question, Variable

_SUFFIX = re.compile(r"O?\d+$")

def _prefix(name: str) -> str:
    return _SUFFIX.sub("", name)

def _is_binary(var: Variable) -> bool:
    codes = {vl.value for vl in var.value_labels}
    return bool(codes) and codes <= {0.0, 1.0}

def _group_text(model: QuestionModel, members: tuple[str, ...]) -> str:
    labels = [model.variables[m].label for m in members]
    stem = os.path.commonprefix(labels).rstrip(" :-")
    return stem or labels[0]


def _group_qid(members: tuple[str, ...]) -> str:
    return _prefix(members[0]).lower() or members[0].lower()


def apply_groups(model: QuestionModel, groups: list[tuple[str, ...]]) -> QuestionModel:
    """Return a new QuestionModel where each `groups` entry becomes one multi
    Question; ungrouped variables keep their single Question. variables dict is
    unchanged. (REQ-C-06, M-02)"""
    grouped = {name for g in groups for name in g}
    questions: list[Question] = []
    for g in groups:
        members = tuple(g)
        questions.append(Question(
            qid=_group_qid(members), kind="multi", variables=members,
            text=_group_text(model, members),
        ))
    for q in model.questions:
        if q.kind == "single" and q.variables[0] not in grouped:
            questions.append(q)
    return QuestionModel(variables=dict(model.variables), questions=questions)


def suggest_multi_groups(model: QuestionModel) -> list[tuple[str, ...]]:
    """Group variables sharing a name prefix that look like a 0/1 tickbox grid.
    A group needs >=2 members all carrying a value-label set subset of {0,1}.
    Returns groups in file (insertion) order. (REQ-M-02, R2)"""
    buckets: "OrderedDict[str, list[str]]" = OrderedDict()
    for name, var in model.variables.items():
        if not _is_binary(var):
            continue
        buckets.setdefault(_prefix(name), []).append(name)
    return [tuple(members) for members in buckets.values() if len(members) >= 2]
