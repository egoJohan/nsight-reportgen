"""The single seam for building a material's QuestionModel with the manual
grouping override applied.

Every material-model load (questions, variables, summary, preview, render, AI)
goes through here so a manual group reshapes the model consistently everywhere.
When no override is stored (or the client can't provide one), this behaves exactly
like the previous ``enrich_model`` auto-detection.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import tempfile
import threading
from collections import OrderedDict

from reportbuilder.ingest.grouping_override import apply_grouping_override
from reportbuilder.ingest.sav_reader import read_sav, sav_file_label
from reportbuilder.model.question import QuestionModel


#: Parsed SAVs, newest last, keyed by the CONTENT of the file.
#:
#: Parsing one costs ~350 ms for a typical study (229 variables, 1000
#: respondents) and every model load paid it — so previewing a sixty-slide deck
#: spent twenty seconds re-reading the same file, on the CPU, while the requests
#: fought each other for it.
#:
#: Keyed by digest rather than by material id, so it cannot go stale: different
#: bytes are a different key, and re-uploading a material can never be served
#: the previous parse. The cost is one hash of the blob per load (a few ms
#: against 350) and holding a handful of DataFrames.
_PARSED: OrderedDict[str, tuple[object, QuestionModel, str]] = OrderedDict()

#: How many to keep. Small on purpose: a study is a few MB in memory and the
#: access pattern is one material at a time, occasionally two while somebody
#: compares waves.
_PARSED_MAX = 4
#: Guards the cache BOOKKEEPING only — never the parse itself, so two materials
#: still parse concurrently. Without it a hit could be evicted by another
#: request between reading the entry and touching it, and `move_to_end` raised
#: KeyError: a 500 for the reader, needing only more materials in play than the
#: cache holds. That is a shared-machine failure, invisible on a one-material
#: dev box.
_PARSED_LOCK = threading.Lock()


def _parse(raw: bytes):
    """Parse a SAV blob, or hand back the parse we already have of it."""
    key = hashlib.sha256(raw).hexdigest()
    with _PARSED_LOCK:
        cached = _PARSED.get(key)
        if cached is not None:
            _PARSED.move_to_end(key)
    if cached is None:
        with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
            tmp.write(raw)
            path = tmp.name
        try:
            df, model = read_sav(path)
            label = sav_file_label(path) or ""
        finally:
            os.unlink(path)
        cached = (df, model, label)
        # Two threads may have parsed the same blob; they produce equal values,
        # so either winning is fine.
        with _PARSED_LOCK:
            _PARSED[key] = cached
            _PARSED.move_to_end(key)
            while len(_PARSED) > _PARSED_MAX:
                _PARSED.popitem(last=False)
    df, model, label = cached
    # The frame is copied and the model is not. Nothing in the codebase mutates
    # either — checked — but a DataFrame is the one people reach for a column
    # assignment on, and a shared one would corrupt the NEXT request rather than
    # this one, which is the worst kind of bug to be handed. A copy is a few ms
    # against the 350 saved. The model is immutable by construction: every
    # transform below builds a new QuestionModel.
    return df.copy(), model, label


def _forget_parsed_savs() -> None:
    """Drop the parse cache. For tests, and for anything that needs to prove it
    is reading from storage."""
    _PARSED.clear()


def _read(material_id: str, client):
    return _parse(client.get_material(material_id))


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


def _finalize(model, material_id: str, client, override: dict | None, df=None):
    """Apply the report's grouping override, then the material's per-question
    cleaning (name overrides + value merges) — so they show consistently
    everywhere the model is used. Config is loaded once."""
    model = apply_grouping_override(model, override or {}, df=df)
    cfg = material_config(material_id, client)
    model = _apply_labels(model, _labels_from_cfg(cfg))
    model = _apply_merges(model, _merges_from_cfg(cfg))
    return model


def raw_model_for_material(material_id: str, client):
    """The file's own model, before any grouping or curation is applied.

    `model_for_material` finalises: the battery grouper relabels each member
    variable to its category, so `"<member>:<shared question>"` becomes just
    `"<member>"`. That is right for charting and wrong for reading a study's
    NAMES out of it — on the Holiday Club file the finalised model kept 77 of
    the file's 192 colon labels, and the sensitive-term proposal, which reads
    exactly that shape, found nothing at all. No proposals meant no gate and no
    registered terms: the masking silently had nothing to mask.

    Which names a dataset contains is a property of the FILE, not of how one
    report happens to group it — and grouping is per-report, so a finalised
    model cannot be the source for something registered per material.
    """
    _df, model, _label = _read(material_id, client)
    return model


def model_for_material(material_id: str, client, override: dict | None = None):
    df, model, _label = _read(material_id, client)
    return _finalize(model, material_id, client, override, df=df)


def df_model_for_material(material_id: str, client, override: dict | None = None):
    df, model, _label = _read(material_id, client)
    return df, _finalize(model, material_id, client, override, df=df)


def df_model_label_for_material(material_id: str, client, override: dict | None = None):
    df, model, label = _read(material_id, client)
    return df, _finalize(model, material_id, client, override, df=df), label
