"""Questions routes: GET /materials/{material_id}/questions (browse),
PUT /materials/{material_id}/grouping (stateless preview),
POST /materials/{material_id}/preview-chart (single-chart PNG thumbnail).
(REQ-C-05, REQ-C-06, REQ-C-13, REQ-C-19, REQ-D-06, M-02)"""
from __future__ import annotations

import hashlib
import os
import pathlib
import shutil
import tempfile
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import rasterize_pages
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.ingest.multi_group import apply_groups, suggest_multi_groups
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.question import QuestionModel
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
)
from reportbuilder.render.plugins import suggest_chart_type
from reportbuilder.stats.series import Cell, SeriesResult
from reportbuilder.store.datahive_client import DataHiveClient


questions_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _quick_series(question, model: QuestionModel) -> SeriesResult:
    """Build a minimal SeriesResult from the question's value-label shape.

    Used exclusively by suggest_chart_type so no real survey data is needed.
    For single questions: categories come from non-missing value labels.
    For multi questions: categories are the member-variable labels.
    (REQ-C-13)
    """
    if question.kind == "multi":
        cats = tuple(model.variables[v].label for v in question.variables)
    else:
        var = model.variables[question.variables[0]]
        cats = tuple(
            vl.label
            for vl in var.value_labels
            if vl.value not in var.missing_values
        )
        if not cats:
            cats = ("A", "B", "C")  # fallback: no value labels defined

    segments = ("Total",)
    cells: dict[tuple[str, str], Cell] = {
        (cat, "Total"): Cell(pct=50.0, count=10.0, mean=None) for cat in cats
    }
    return SeriesResult(
        categories=cats,
        segments=segments,
        cells=cells,
        base_n={"Total": len(cats) * 10},
        statistic="pct",
    )


def _missing_value_list(model: QuestionModel, qid: str) -> list[dict]:
    """Return the missing-value mapping for a question as a list of dicts.

    Each entry has ``{"code": float, "label": str}``.  Empty list when none.
    (REQ-D-06)
    """
    try:
        pairs = model.missing_value_labels(qid)
    except (KeyError, IndexError):
        return []
    return [{"code": code, "label": label} for code, label in pairs]


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
    render-resolvable. Each question includes a suggested chart type (REQ-C-13) and the
    missing-value mapping (REQ-D-06). (REQ-C-05)"""
    model = load_model_for_material(material_id, client)
    return {
        "questions": [
            {
                "qid": q.qid,
                "kind": q.kind,
                "variables": list(q.variables),
                "text": q.text,
                "suggested_chart_type": suggest_chart_type(q, _quick_series(q, model)),
                "missing_values": _missing_value_list(model, q.qid),
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
            status_code=500,
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


# ---------------------------------------------------------------------------
# W1.2 — Single-chart live-preview endpoint (REQ-C-19, REQ-C-13)
# ---------------------------------------------------------------------------


class _NumberFormatBody(BaseModel):
    mode: str = "auto"
    pct_decimals: int = 0
    mean_decimals: int = 1
    count_round_up: bool = False
    show_pct_sign: bool = True


class _SortSpecBody(BaseModel):
    basis: str = "data_order"
    topbox_codes: list[float] = []
    descending: bool = True


class _ElementTogglesBody(BaseModel):
    title: bool = True
    legend: bool = True
    n: bool = True
    axis_names: bool = True
    filter_var: bool = True
    data_labels: bool = True


class ChartSpecBody(BaseModel):
    """Request body for POST /materials/{material_id}/preview-chart.

    Mirrors ChartSpec fields.  ``template_slot`` defaults to "preview" because
    the wizard doesn't assign slots; the preview always renders a single blank slide.
    (REQ-C-05, REQ-C-13, REQ-C-19, REQ-D-06)
    """

    question_ref: str
    chart_type: str
    statistic: str = "pct"
    classifying_var: str | None = None
    number_format: _NumberFormatBody = _NumberFormatBody()
    sort: _SortSpecBody = _SortSpecBody()
    elements: _ElementTogglesBody = _ElementTogglesBody()
    scatter_xy: list[str] | None = None
    show_not_answered: bool = False


def _chart_spec_from_body(body: ChartSpecBody) -> ChartSpec:
    """Convert the Pydantic request body to a ChartSpec dataclass."""
    return ChartSpec(
        question_ref=body.question_ref,
        chart_type=body.chart_type,
        statistic=body.statistic,
        classifying_var=body.classifying_var,
        number_format=NumberFormat(
            mode=body.number_format.mode,
            pct_decimals=body.number_format.pct_decimals,
            mean_decimals=body.number_format.mean_decimals,
            count_round_up=body.number_format.count_round_up,
            show_pct_sign=body.number_format.show_pct_sign,
        ),
        sort=SortSpec(
            basis=body.sort.basis,
            topbox_codes=tuple(body.sort.topbox_codes),
            descending=body.sort.descending,
        ),
        template_slot="preview",
        elements=ElementToggles(
            title=body.elements.title,
            legend=body.elements.legend,
            n=body.elements.n,
            axis_names=body.elements.axis_names,
            filter_var=body.elements.filter_var,
            data_labels=body.elements.data_labels,
        ),
        scatter_xy=tuple(body.scatter_xy) if body.scatter_xy is not None else None,
        show_not_answered=body.show_not_answered,
    )


def _preview_out_dir(material_id: str, spec_json: str) -> pathlib.Path:
    """Return a deterministic per-(material, spec) temp directory for preview artifacts."""
    key = hashlib.md5(f"{material_id}:{spec_json}".encode()).hexdigest()[:16]
    d = pathlib.Path(tempfile.gettempdir()) / "nsight-preview" / key
    d.mkdir(parents=True, exist_ok=True)
    return d


@questions_router.post("/materials/{material_id}/preview-chart")
def preview_chart(
    material_id: str,
    body: ChartSpecBody,
    client: DataHiveClient = Depends(get_client),
) -> Response:
    """Render a single ChartSpec as a PNG thumbnail for the wizard's live preview.

    Implementation: loads the material, builds a 1-ChartSpec image-mode Report,
    calls build_pptx → pptx_to_pdf → rasterize page 1 → returns PNG bytes.
    Requires LibreOffice (soffice) on PATH; returns 503 if absent.
    Chart ValueErrors (e.g. scatter without scatter_xy) become 422. (REQ-C-05, REQ-C-13, REQ-C-19, REQ-D-06)
    """
    # Guard: LibreOffice required for PDF conversion
    if shutil.which("soffice") is None and shutil.which("libreoffice") is None:
        raise HTTPException(
            status_code=503,
            detail="LibreOffice (soffice) is not available; chart preview requires it.",
        )

    # 1. Load material data
    raw = client.get_material(material_id)
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        df, model = read_sav(tmp_path)
    finally:
        os.unlink(tmp_path)

    groups = suggest_multi_groups(model)
    if groups:
        model = apply_groups(model, groups)

    # 2. Convert request body to ChartSpec
    spec = _chart_spec_from_body(body)

    # 3. Wrap in a 1-chart image-mode Report
    report = Report(
        name="preview",
        render_mode="image",
        template_ref="",
        charts=(spec,),
    )

    # 4. Render PPTX → PDF → PNG page 1
    out_dir = _preview_out_dir(material_id, body.model_dump_json())
    pptx_path = str(out_dir / "preview.pptx")
    try:
        build_pptx(report, model, df, pptx_path)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    pdf_path = pptx_to_pdf(pptx_path, str(out_dir))
    pngs = rasterize_pages(pdf_path, str(out_dir / "pages"))

    if not pngs:
        raise HTTPException(status_code=500, detail="Rasterization produced no pages.")

    png_bytes = pathlib.Path(pngs[0]).read_bytes()
    return Response(content=png_bytes, media_type="image/png")
