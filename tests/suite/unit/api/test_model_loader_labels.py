"""model_loader applies per-material question-label overrides (case-page rename).

A renamed question flows through the single model-load seam, so it shows renamed
everywhere (questions list, report charts, preview, deck, AI). Blank = revert.
"""
from __future__ import annotations

import json

from reportbuilder.api.model_loader import model_for_material
from reportbuilder.store.memory_client import InMemoryDataHiveClient
from reportbuilder.testing.fixtures import synthetic_sav


def _client_with_material(tmp_path):
    c = InMemoryDataHiveClient(storage_dir=str(tmp_path / "s"))
    case = c.create_case("A")
    with open(synthetic_sav(tmp_path), "rb") as f:
        mid = c.attach_material(case, "s.sav", f.read(), "cb")
    return c, mid


def test_applies_question_label_override(tmp_path):
    c, mid = _client_with_material(tmp_path)
    c.save_material_config(mid, json.dumps({"question_labels": {"q1": "Renamed Q1"}}))
    q1 = next(q for q in model_for_material(mid, c).questions if q.qid == "q1")
    assert q1.text == "Renamed Q1"


def test_blank_label_keeps_original(tmp_path):
    c, mid = _client_with_material(tmp_path)
    original = next(q for q in model_for_material(mid, c).questions if q.qid == "q1").text
    c.save_material_config(mid, json.dumps({"question_labels": {"q1": ""}}))
    q1 = next(q for q in model_for_material(mid, c).questions if q.qid == "q1")
    assert q1.text == original


def test_no_config_is_noop(tmp_path):
    c, mid = _client_with_material(tmp_path)
    # No material config saved at all — original labels preserved.
    q1 = next(q for q in model_for_material(mid, c).questions if q.qid == "q1")
    assert q1.text and q1.text != "Renamed Q1"
