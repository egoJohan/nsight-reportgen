"""Questions routes: GET /materials/{material_id}/questions (browse),
PUT /materials/{material_id}/grouping (stateless preview). (REQ-C-05, REQ-C-06, M-02)"""
from __future__ import annotations

import os
import tempfile

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.ingest.multi_group import apply_groups, suggest_multi_groups
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.question import QuestionModel
from reportbuilder.store.datahive_client import DataHiveClient


questions_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_singles(material_id: str, client: DataHiveClient) -> QuestionModel:
    """Fetch the material's raw bytes from the store and return the QuestionModel as produced
    directly by read_sav (all single questions, no auto-grouping). Used by the stateless grouping
    endpoint so it can apply user-requested grouping from a clean slate."""
    raw = client.get_material(material_id)
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        _df, model = read_sav(tmp_path)
    finally:
        os.unlink(tmp_path)
    return model


def load_model_for_material(material_id: str, client: DataHiveClient) -> QuestionModel:
    """Fetch the material's stored .sav bytes from the store and build the QuestionModel with
    auto-detected multi groups applied (render-resolvable qids). Manual-grouping persistence is
    deferred to Phase 4. (REQ-C-05)"""
    model = _load_singles(material_id, client)
    groups = suggest_multi_groups(model)
    if groups:
        return apply_groups(model, groups)
    return model


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@questions_router.get("/materials/{material_id}/questions")
def list_questions(
    material_id: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Browse all questions for a material. Auto-detected multi groups are pre-applied so qids are
    render-resolvable. (REQ-C-05)"""
    model = load_model_for_material(material_id, client)
    return {
        "questions": [
            {
                "qid": q.qid,
                "kind": q.kind,
                "variables": list(q.variables),
                "text": q.text,
            }
            for q in model.questions
        ]
    }


class GroupingRequest(BaseModel):
    """Request body for PUT /materials/{material_id}/grouping."""
    variables: list[str]
    kind: str  # "single" | "multi"


@questions_router.put("/materials/{material_id}/grouping")
def set_grouping(
    material_id: str,
    body: GroupingRequest,
    client: DataHiveClient = Depends(get_client),
) -> object:
    """Stateless preview of a grouping override — applies the requested single/multi grouping to a
    freshly-loaded model and returns the resulting question(s). Does NOT persist. Persistence of
    manual single/multi overrides is DEFERRED to Phase 4 (datahive material metadata).
    (REQ-C-06, M-02)"""
    base = _load_singles(material_id, client)

    if body.kind == "multi":
        grouped_model = apply_groups(base, [tuple(body.variables)])
        # Find the question whose variables match the requested set
        var_set = tuple(body.variables)
        for q in grouped_model.questions:
            if q.variables == var_set:
                return {"qid": q.qid, "kind": q.kind, "variables": list(q.variables), "text": q.text}
        # Fallback: return first multi question (should not happen)
        for q in grouped_model.questions:
            if q.kind == "multi":
                return {"qid": q.qid, "kind": q.kind, "variables": list(q.variables), "text": q.text}

    # kind == "single": return individual single question(s) for each requested variable
    result = []
    for var_name in body.variables:
        for q in base.questions:
            if q.kind == "single" and q.variables == (var_name,):
                result.append({"qid": q.qid, "kind": q.kind, "variables": list(q.variables), "text": q.text})
                break
    return result
