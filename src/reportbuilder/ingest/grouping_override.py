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

from reportbuilder.model.question import QuestionModel
from reportbuilder.ingest.multi_group import _is_binary, apply_groups, suggest_multi_groups
from reportbuilder.ingest.battery_group import apply_batteries, suggest_batteries


def _battery_vars(battery) -> set[str]:
    _subject, cells = battery
    return {var for (_cat, var, _stem) in cells}


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
    forced = (set(override.get("singles", []) or []) & known) - manual_members
    blocked = manual_members | forced

    # Auto multi suggestions that don't touch a manual member or a forced single.
    auto_multi = [g for g in suggest_multi_groups(model) if not (set(g) & blocked)]
    all_multi = manual_groups + auto_multi
    m = apply_groups(model, all_multi) if all_multi else model
    m = _inject_labels(m, override.get("groups", []) or [])

    # Auto batteries that don't touch a manual member or a forced single.
    bats = [b for b in suggest_batteries(m) if not (_battery_vars(b) & blocked)]
    if bats:
        m = apply_batteries(m, bats)
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
