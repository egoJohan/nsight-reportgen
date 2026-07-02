"""Apply a manual grouping override on top of auto-detection.

Rule: manual groups win; forced singles stay single; auto-detection fills the
gaps. Operates on the RAW read_sav model (before enrich) and returns the reshaped
QuestionModel. See docs/superpowers/specs/2026-07-01-manual-grouping-override-design.md.

The override is a small dict::

    {"groups": [{"kind": "multi", "variables": [...], "label": "..."}], "singles": [...]}

``kind == "battery"`` is reserved for Phase 2 — tolerated and skipped here.
"""
from __future__ import annotations

import dataclasses

from reportbuilder.model.question import Question, QuestionModel, Variable
from reportbuilder.ingest.multi_group import (
    _is_binary, _group_text, apply_groups, suggest_multi_groups,
)
from reportbuilder.ingest.battery_group import _slug, apply_batteries, suggest_batteries


def _battery_vars(battery) -> set[str]:
    _subject, cells = battery
    return {var for (_cat, var, _stem) in cells}


def _scale_sig(var: Variable):
    """A hashable signature of a variable's rating scale (code→label), or None if the
    variable isn't a scale. Two variables share a scale when their signatures match."""
    from reportbuilder.stats.engine import scale_levels
    lv = scale_levels(var)
    return tuple((c, l) for c, l, _p in lv) if lv else None


def _apply_manual_batteries(model: QuestionModel,
                            batteries: list[tuple[str, tuple[str, ...]]]) -> QuestionModel:
    """Replace each battery's member single-questions with one ``kind="battery"``
    question at the position of the first member (deck order preserved). The text is
    the user's typed name, else the SHARED question stem of the members (not their
    labels concatenated); members are relabelled to their subject for clean
    stacked-bar statements; the qid is a short, stable slug."""
    if not batteries:
        return model
    # Text derived from ORIGINAL labels (before the subject relabel below).
    texts: dict[tuple[str, ...], str] = {
        members: ((label or "").strip() or _group_text(model, members))
        for label, members in batteries
    }
    variables = dict(model.variables)
    for _label, members in batteries:
        for v in members:
            lbl = variables[v].label or ""
            if ":" in lbl:
                subj = lbl.split(":", 1)[0].strip()
                if subj:
                    variables[v] = dataclasses.replace(variables[v], label=subj)

    by_var = {v: members for _label, members in batteries for v in members}
    used_qids: set[str] = set()

    def _qid(text: str, members: tuple[str, ...]) -> str:
        base = _slug(text)[:48].strip("-") or _slug("-".join(members))[:48]
        qid = f"battery-{base}"
        cand, i = qid, 2
        while cand in used_qids:
            cand, i = f"{qid}-{i}", i + 1
        used_qids.add(cand)
        return cand

    emitted: set[tuple[str, ...]] = set()
    questions: list[Question] = []
    for q in model.questions:
        hit = set(q.variables) & set(by_var)
        if not hit:
            questions.append(q)
            continue
        members = by_var[next(iter(hit))]
        if members in emitted:
            continue
        emitted.add(members)
        questions.append(Question(qid=_qid(texts[members], members), kind="battery",
                                  variables=tuple(members), text=texts[members]))
    return QuestionModel(variables=variables, questions=questions)


def apply_grouping_override(model: QuestionModel, override: dict | None) -> QuestionModel:
    override = override or {}
    known = set(model.variables)

    # Manual multi groups — applied leniently: only valid ones (≥2 known,
    # tick-box/binary members) are used; anything else (stale/removed variable,
    # non-tick-box, battery-kind) is silently skipped so a stored-but-now-invalid
    # grouping never breaks the model. Authoring is validated in the UI.
    manual_groups: list[tuple[str, ...]] = []
    for g in override.get("groups", []) or []:
        if g.get("kind") != "multi":
            continue
        vs = tuple(g.get("variables", []) or [])
        if (
            len(vs) >= 2
            and set(vs) <= known
            and all(_is_binary(model.variables[v]) for v in vs)
        ):
            manual_groups.append(vs)
    manual_members = {v for g in manual_groups for v in g}

    # Manual BATTERY groups — ≥2 known members that are rating scales sharing one scale
    # signature; anything else silently skipped (lenient, like multi). Members are
    # blocked from auto grouping and dropped from singles.
    manual_batteries: list[tuple[str, tuple[str, ...]]] = []
    for g in override.get("groups", []) or []:
        if g.get("kind") != "battery":
            continue
        vs = tuple(g.get("variables", []) or [])
        if len(vs) < 2 or not (set(vs) <= known):
            continue
        sigs = [_scale_sig(model.variables[v]) for v in vs]
        if all(sigs) and len(set(sigs)) == 1:
            manual_batteries.append((g.get("label") or "", vs))
    battery_members = {v for _label, members in manual_batteries for v in members}

    forced = (set(override.get("singles", []) or []) & known) - manual_members - battery_members
    blocked = manual_members | forced | battery_members

    # Auto multi suggestions that don't touch a manual member or a forced single.
    auto_multi = [g for g in suggest_multi_groups(model) if not (set(g) & blocked)]
    all_multi = manual_groups + auto_multi
    m = apply_groups(model, all_multi) if all_multi else model
    m = _inject_labels(m, override.get("groups", []) or [])

    # Auto batteries that don't touch a manual member or a forced single.
    bats = [b for b in suggest_batteries(m) if not (_battery_vars(b) & blocked)]
    if bats:
        m = apply_batteries(m, bats)

    # Manual batteries applied last — members are still single here (blocked above).
    m = _apply_manual_batteries(m, manual_batteries)
    return m


def _inject_labels(model: QuestionModel, groups: list) -> QuestionModel:
    labels = {
        tuple(g.get("variables", []) or []): g["label"]
        for g in groups
        if g.get("kind") == "multi" and g.get("label")
    }
    if not labels:
        return model
    questions = [
        dataclasses.replace(q, text=labels[tuple(q.variables)])
        if q.kind == "multi" and tuple(q.variables) in labels
        else q
        for q in model.questions
    ]
    return QuestionModel(variables=model.variables, questions=questions)
