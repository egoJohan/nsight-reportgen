"""The single seam for building a material's QuestionModel with the manual
grouping override applied.

Every material-model load (questions, variables, summary, preview, render, AI)
goes through here so a manual group reshapes the model consistently everywhere.
When no override is stored (or the client can't provide one), this behaves exactly
like the previous ``enrich_model`` auto-detection.
"""
from __future__ import annotations

import json
import os
import tempfile

from reportbuilder.ingest.grouping_override import apply_grouping_override
from reportbuilder.ingest.sav_reader import read_sav, sav_file_label


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


def model_for_material(material_id: str, client, override: dict | None = None):
    _df, model, _label = _read(material_id, client)
    return apply_grouping_override(model, override or {})


def df_model_for_material(material_id: str, client, override: dict | None = None):
    df, model, _label = _read(material_id, client)
    return df, apply_grouping_override(model, override or {})


def df_model_label_for_material(material_id: str, client, override: dict | None = None):
    df, model, label = _read(material_id, client)
    return df, apply_grouping_override(model, override or {}), label
