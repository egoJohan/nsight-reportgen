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


def question_labels(material_id: str, client) -> dict[str, str]:
    """The per-material question-name overrides ({qid: custom label}) stored in
    the material config. Missing/blank/malformed → no overrides."""
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
        labels = (json.loads(raw) or {}).get("question_labels")
    except (ValueError, TypeError):
        return {}
    if not isinstance(labels, dict):
        return {}
    # Only non-blank overrides count (blank = revert to the SAV label).
    return {qid: text for qid, text in labels.items() if isinstance(text, str) and text.strip()}


def _apply_labels(model: QuestionModel, labels: dict[str, str]) -> QuestionModel:
    if not labels:
        return model
    questions = [
        dataclasses.replace(q, text=labels[q.qid]) if q.qid in labels else q
        for q in model.questions
    ]
    return QuestionModel(variables=model.variables, questions=questions)


def _finalize(model, material_id: str, client, override: dict | None):
    """Apply the report's grouping override, then the material's question-name
    overrides — so a rename shows consistently everywhere the model is used."""
    model = apply_grouping_override(model, override or {})
    return _apply_labels(model, question_labels(material_id, client))


def model_for_material(material_id: str, client, override: dict | None = None):
    _df, model, _label = _read(material_id, client)
    return _finalize(model, material_id, client, override)


def df_model_for_material(material_id: str, client, override: dict | None = None):
    df, model, _label = _read(material_id, client)
    return df, _finalize(model, material_id, client, override)


def df_model_label_for_material(material_id: str, client, override: dict | None = None):
    df, model, label = _read(material_id, client)
    return df, _finalize(model, material_id, client, override), label
