"""Questions routes: GET /materials/{material_id}/questions (browse),
PUT /materials/{material_id}/grouping (stateless preview). (REQ-C-05, REQ-C-06, M-02)"""
from __future__ import annotations

import os
import tempfile
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
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
    kind: Literal["single", "multi"]


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
        var_set = tuple(body.variables)
        # Order-independent binary-eligibility validation (REQ-C-06, M-02):
        # A valid multi group requires >=2 variables, all known, none of them a scale.
        if len(var_set) < 2:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"A multi group requires at least 2 variables; got {list(body.variables)}."
                ),
            )
        unknown = [v for v in var_set if v not in base.variables]
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Unknown variable(s) {unknown} — not present in the material."
                ),
            )
        scale_vars = [v for v in var_set if base.variables[v].measurement == "scale"]
        if scale_vars:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Scale variable(s) {scale_vars} cannot be members of a multi group. "
                    "Multi-response groups must be binary/categorical tick-box variables."
                ),
            )
        grouped_model = apply_groups(base, [var_set])
        var_set_sorted = tuple(sorted(var_set))
        for q in grouped_model.questions:
            if q.kind == "multi" and tuple(sorted(q.variables)) == var_set_sorted:
                return {"qid": q.qid, "kind": q.kind, "variables": list(q.variables), "text": q.text}
        # Defensive: apply_groups always produces exactly the requested group; this is an internal error.
        raise HTTPException(
            status_code=422,
            detail=(
                f"The variables {list(body.variables)} could not be resolved to a multi group "
                "after grouping. This is an internal error."
            ),
        )

    # kind == "single": return individual single question(s) for each requested variable
    result = []
    for var_name in body.variables:
        for q in base.questions:
            if q.kind == "single" and q.variables == (var_name,):
                result.append({"qid": q.qid, "kind": q.kind, "variables": list(q.variables), "text": q.text})
                break
    return result
