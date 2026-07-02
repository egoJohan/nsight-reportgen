"""Battery grouping — collapse a 2D rating grid into one battery per subject.

Survey platforms export rating grids as one variable per (row × column) cell,
labelled ``"<category>:<subject>:<question>"`` (e.g. brand image:
``"Inhimillinen:Attendo: Arvioi mielikuvaasi…"``).  Listed individually that's
dozens of cryptic rows.  This module detects that pattern generically and groups
the cells **by subject** (the 2nd label segment) into one ``kind="battery"``
question per subject, whose members are the categories (1st segment).

Generic: nothing here is specific to brand image — any `<category>:<subject>:…`
rating grid is grouped the same way.  The battery's per-category statistic
(default: the mean rating) is computed by the stats engine.
"""
from __future__ import annotations

import dataclasses
import os
import re
from collections import OrderedDict

from reportbuilder.model.question import QuestionModel, Question, Variable  # noqa: F401


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "x"


def _cells(model: QuestionModel) -> list[tuple[str, str, str, str]]:
    """Grid cells among the model's SINGLE questions: (category, subject, var, stem)."""
    out: list[tuple[str, str, str, str]] = []
    for q in model.questions:
        if q.kind != "single" or not q.variables:
            continue
        var = model.variables.get(q.variables[0])
        if var is None:
            continue
        parts = (var.label or "").split(":")
        if len(parts) >= 3:
            cat = parts[0].strip()
            subj = parts[1].strip()
            stem = ":".join(parts[2:]).strip()
            if cat and subj:
                out.append((cat, subj, q.variables[0], stem))
    return out


def suggest_batteries(
    model: QuestionModel, *, min_members: int = 3, min_subjects: int = 2
) -> list[tuple[str, list[tuple[str, str, str]]]]:
    """Return ``[(subject, [(category, var, stem), …]), …]`` — one battery per
    subject. Qualifies only when there are >= min_subjects subjects each with
    >= min_members cells (a genuine grid, not a one-off labelled with colons)."""
    cells = _cells(model)
    if not cells:
        return []
    by_subject: "OrderedDict[str, list[tuple[str, str, str]]]" = OrderedDict()
    for cat, subj, var, stem in cells:
        by_subject.setdefault(subj, []).append((cat, var, stem))
    qualifying = [s for s, m in by_subject.items() if len(m) >= min_members]
    if len(qualifying) < min_subjects:
        return []
    return [(s, by_subject[s]) for s in by_subject if len(by_subject[s]) >= min_members]


def _battery_text(subject: str, stems: list[str]) -> str:
    """`<subject> — <shared question>` (the question shared by all cells).

    The theme is the common prefix of the cell stems. Survey stems commonly append
    scale/answer instructions after the question ("… mielikuvaasi? Vastaa asteikolla
    1-5 …"), so keep the whole question by cutting at its terminal "?"; drop the
    trailing legend. With no sentence terminator, trim a very long theme at a word
    boundary (never mid-sentence at an arbitrary length). (REQ-C-24a)
    """
    theme = re.sub(r"\s+", " ", os.path.commonprefix(stems)).strip(" :-")
    if not theme:
        return subject
    q = re.match(r"(.*?\?)(?:\s|$)", theme)  # up to the first sentence-ending "?"
    if q:
        theme = q.group(1)
    elif len(theme) > 160:
        theme = theme[:160].rsplit(" ", 1)[0] + "…"
    return f"{subject} — {theme}"


def apply_batteries(
    model: QuestionModel, batteries: list[tuple[str, list[tuple[str, str, str]]]]
) -> QuestionModel:
    """Return a new model where each battery's cells become one ``battery``
    question (members = the cells), their labels rewritten to the category, and
    the consumed single questions removed."""
    if not batteries:
        return model
    variables = dict(model.variables)
    consumed: set[str] = set()
    battery_qs: list[Question] = []
    used_qids: set[str] = set()

    for subject, members in batteries:
        names = tuple(var for (_cat, var, _stem) in members)
        consumed.update(names)
        for cat, var, _stem in members:
            if cat and cat != variables[var].label:
                variables[var] = dataclasses.replace(variables[var], label=cat)
        qid = f"battery-{_slug(subject)}"
        # Disambiguate in the unlikely event two subjects slug-collide.
        base = qid
        i = 2
        while qid in used_qids:
            qid = f"{base}-{i}"
            i += 1
        used_qids.add(qid)
        battery_qs.append(Question(
            qid=qid, kind="battery", variables=names,
            text=_battery_text(subject, [stem for (_c, _v, stem) in members]),
        ))

    kept = [
        q for q in model.questions
        if not (q.kind == "single" and q.variables and q.variables[0] in consumed)
    ]
    return QuestionModel(variables=variables, questions=battery_qs + kept)
