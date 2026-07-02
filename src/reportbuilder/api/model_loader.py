"""The single seam for building a material's QuestionModel with the manual
grouping override applied.

Every material-model load (questions, variables, summary, preview, render, AI)
goes through here so a manual group reshapes the model consistently everywhere.
When no override is stored (or the client can't provide one), this behaves exactly
like the previous ``enrich_model`` auto-detection.
"""
from __future__ import annotations

import dataclasses
import json
import os
import tempfile

from reportbuilder.ingest.grouping_override import apply_grouping_override
from reportbuilder.ingest.sav_reader import read_sav, sav_file_label
from reportbuilder.model.question import QuestionModel


def _read(material_id: str, client):
    raw = client.get_material(material_id)
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        path = tmp.name
    try:
        df, model = read_sav(path)
        label = sav_file_label(path) or ""
    finally:
        os.unlink(path)
    return df, model, label


def material_config(material_id: str, client) -> dict:
    """Parsed per-material config dict (question_labels, value_merges, …).
    Missing/malformed → {}."""
    loader = getattr(client, "load_material_config", None)
    if loader is None:
        return {}
    try:
        raw = loader(material_id)
    except Exception:
        return {}
    if not raw:
        return {}
    try:
        cfg = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def _labels_from_cfg(cfg: dict) -> dict[str, str]:
    labels = cfg.get("question_labels")
    if not isinstance(labels, dict):
        return {}
    # Only non-blank overrides count (blank = revert to the SAV label).
    return {qid: text for qid, text in labels.items() if isinstance(text, str) and text.strip()}


def question_labels(material_id: str, client) -> dict[str, str]:
    """The per-material question-name overrides ({qid: custom label})."""
    return _labels_from_cfg(material_config(material_id, client))


def value_merges(material_id: str, client) -> dict[str, tuple[tuple[str, tuple[str, ...]], ...]]:
    """Per-qid value merges, normalised to {qid: ((label, (member, …)), …)}."""
    return _merges_from_cfg(material_config(material_id, client))


def _merges_from_cfg(cfg: dict) -> dict[str, tuple[tuple[str, tuple[str, ...]], ...]]:
    """Per-qid value merges: stored as {qid: [[label, member, …], …]} → normalised
    to {qid: ((label, (member, …)), …)}. Groups need a label + ≥1 member."""
    raw = cfg.get("value_merges")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, tuple] = {}
    for qid, groups in raw.items():
        parsed = [
            (str(g[0]), tuple(str(m) for m in g[1:]))
            for g in (groups or [])
            if isinstance(g, list) and len(g) >= 2
        ]
        if parsed:
            out[qid] = tuple(parsed)
    return out


def _apply_labels(model: QuestionModel, labels: dict[str, str]) -> QuestionModel:
    if not labels:
        return model
    questions = [
        dataclasses.replace(q, text=labels[q.qid]) if q.qid in labels else q
        for q in model.questions
    ]
    return QuestionModel(variables=model.variables, questions=questions)


def _apply_merges(model: QuestionModel, merges: dict) -> QuestionModel:
    if not merges:
        return model
    questions = [
        dataclasses.replace(q, value_merges=merges[q.qid]) if q.qid in merges else q
        for q in model.questions
    ]
    return QuestionModel(variables=model.variables, questions=questions)


def _finalize(model, material_id: str, client, override: dict | None):
    """Apply the report's grouping override, then the material's per-question
    cleaning (name overrides + value merges) — so they show consistently
    everywhere the model is used. Config is loaded once."""
    model = apply_grouping_override(model, override or {})
    cfg = material_config(material_id, client)
    model = _apply_labels(model, _labels_from_cfg(cfg))
    model = _apply_merges(model, _merges_from_cfg(cfg))
    return model


def model_for_material(material_id: str, client, override: dict | None = None):
    _df, model, _label = _read(material_id, client)
    return _finalize(model, material_id, client, override)


def df_model_for_material(material_id: str, client, override: dict | None = None):
    df, model, _label = _read(material_id, client)
    return df, _finalize(model, material_id, client, override)


def df_model_label_for_material(material_id: str, client, override: dict | None = None):
    df, model, label = _read(material_id, client)
    return df, _finalize(model, material_id, client, override), label
