"""Multi-question grouping heuristics (REQ-C-06, REQ-M-02).

Two strategies are combined:

1. **var<N>O<M> option families** (A0.2): variables whose names match
   ``^(var\\d+)[Oo]\\d+$`` share a stem ``var<N>`` and are collapsed into
   ONE multi Question regardless of measurement type.  This handles both
   binary tick-box grids (var18O45..53) and ranked/text slot families
   (var17O35..44).

2. **Prefix / binary heuristic** (original): remaining binary (0/1)
   variables are grouped by their name-prefix stem.  Kept for tick-box
   grids that don't follow the O-pattern naming convention.

``_group_text`` understands the ``Brand:Question`` label convention used in
brand-tracking surveys: when every member label has the form
``<Option>:<SharedQuestion>``, the right-hand side becomes the question text
and the left-hand sides are the option (category) labels.
"""
from __future__ import annotations

import dataclasses
import os
import re
from collections import OrderedDict

from reportbuilder.model.question import QuestionModel, Question, Variable

# ---- internal helpers -------------------------------------------------------

_SUFFIX = re.compile(r"O?\d+$")

# A0.2: explicit O-pattern family detector
_O_PATTERN = re.compile(r"^(var\d+)[Oo]\d+$", re.IGNORECASE)


def _prefix(name: str) -> str:
    return _SUFFIX.sub("", name)


def _is_binary(var: Variable) -> bool:
    codes = {vl.value for vl in var.value_labels}
    return bool(codes) and codes <= {0.0, 1.0}


def _group_text(model: QuestionModel, members: tuple[str, ...]) -> str:
    """Derive a question text from the member variable labels.

    Handles the ``Brand:Question`` pattern common in brand-tracking surveys,
    where labels look like ``"Attendo:Mitä seuraavista…"`` or
    ``"1 :Mitä hoivapalveluita…"``.  When all members share the same
    right-hand side after the first ``:``, that shared text is returned as
    the question text.

    Falls back to the common string prefix (stripped of trailing ``: -``)
    or the first label when no common stem can be found.
    """
    labels = [model.variables[m].label for m in members]

    # Brand:Question pattern — split on ":" and check for a shared right side
    if ":" in labels[0]:
        parts = [lbl.split(":", 1) for lbl in labels]
        if all(len(p) == 2 for p in parts):
            right_parts = [p[1].strip() for p in parts]
            if len(set(right_parts)) == 1 and right_parts[0]:
                return right_parts[0]

    # Fallback: common string prefix
    stem = os.path.commonprefix(labels).rstrip(" :-")
    return stem or labels[0]


def _group_qid(members: tuple[str, ...]) -> str:
    return _prefix(members[0]).lower() or members[0].lower()


def _option_labels(model: QuestionModel, members: tuple[str, ...]) -> dict[str, str] | None:
    """When member labels follow ``<Option>:<SharedQuestion>`` (the survey-export
    convention) return ``{member_name: option}`` — i.e. the labels with the shared
    question suffix stripped, so category labels are the actual options. Returns
    None when the pattern does not hold (labels left untouched).
    """
    labels = [model.variables[m].label for m in members]
    if not labels or ":" not in labels[0]:
        return None
    parts = [lbl.split(":", 1) for lbl in labels]
    if not all(len(p) == 2 for p in parts):
        return None
    rights = [p[1].strip() for p in parts]
    # Same shared question on the right for every member → left parts are options.
    if len(set(rights)) == 1 and rights[0]:
        return {m: p[0].strip() for m, p in zip(members, parts) if p[0].strip()}
    return None


# ---- public API -------------------------------------------------------------

def apply_groups(model: QuestionModel, groups: list[tuple[str, ...]]) -> QuestionModel:
    """Return a new QuestionModel where each `groups` entry becomes one multi
    Question; ungrouped variables keep their single Question. variables dict is
    unchanged. (REQ-C-06, M-02)"""
    grouped = {name for g in groups for name in g}
    variables = dict(model.variables)
    questions: list[Question] = []
    for g in groups:
        members = tuple(g)
        # Derive the question text from the ORIGINAL labels first, then strip the
        # shared question suffix off each member so its label is the option only.
        text = _group_text(model, members)
        opts = _option_labels(model, members)
        if opts:
            for name, option in opts.items():
                if option and option != variables[name].label:
                    variables[name] = dataclasses.replace(variables[name], label=option)
        questions.append(Question(
            qid=_group_qid(members), kind="multi", variables=members, text=text,
        ))
    for q in model.questions:
        if q.kind == "single" and q.variables[0] not in grouped:
            questions.append(q)
    return QuestionModel(variables=variables, questions=questions)


def suggest_multi_groups(model: QuestionModel) -> list[tuple[str, ...]]:
    """Suggest multi-question groups using two complementary strategies.

    **Strategy 1 — var<N>O<M> option families (A0.2, REQ-M-02):**
    Variable names matching ``^(var\\d+)[Oo]\\d+$`` are grouped by their
    ``var<N>`` stem.  Requires ≥ 2 members in file order.  This covers
    both binary tick-box grids and scale/text slot families.

    **Strategy 2 — prefix/binary heuristic (REQ-M-02, R2):**
    Remaining binary (0/1 value-label) variables are grouped by their
    name prefix (trailing ``O?\\d+`` stripped).  Requires ≥ 2 members.

    Returns groups in file (insertion) order: O-pattern groups first, then
    prefix/binary groups.
    """
    # --- Strategy 1: var<N>O<M> families ---
    o_buckets: OrderedDict[str, list[str]] = OrderedDict()
    for name in model.variables:
        m = _O_PATTERN.match(name)
        if m:
            stem = m.group(1).lower()
            o_buckets.setdefault(stem, []).append(name)

    o_groups = [tuple(members) for members in o_buckets.values() if len(members) >= 2]
    o_members: set[str] = {name for g in o_groups for name in g}

    # --- Strategy 2: prefix/binary heuristic (for vars not already in an O group) ---
    prefix_buckets: OrderedDict[str, list[str]] = OrderedDict()
    for name, var in model.variables.items():
        if name in o_members:
            continue
        if not _is_binary(var):
            continue
        prefix_buckets.setdefault(_prefix(name), []).append(name)

    prefix_groups = [
        tuple(members) for members in prefix_buckets.values() if len(members) >= 2
    ]

    return o_groups + prefix_groups
