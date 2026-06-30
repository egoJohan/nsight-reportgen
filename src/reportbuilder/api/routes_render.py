"""Render router: orchestrate the full export chain (REQ-C-19, REQ-C-21, REQ-C-22).

POST /cases/{case_id}/reports/{report_id}/render
  body: {"material_id": str, "view"?: "slides"|"pages"}
  returns: {"pptx": <path>, "pdf": <path>, "preview": [<png paths>], "pdf_url": <url>}

GET /cases/{case_id}/reports/{report_id}/preview.pdf
  streams the rendered PDF (REQ-C-19, REQ-C-21)
"""
from __future__ import annotations

import pathlib
import tempfile
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import page_view, slide_view
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import report_from_json
from reportbuilder.store.datahive_client import DataHiveClient

render_router = APIRouter()


# ---------------------------------------------------------------------------
# Deterministic per-report output directory (REQ-C-19, REQ-C-21)
# ---------------------------------------------------------------------------


def render_output_dir(case_id: str, report_id: str) -> pathlib.Path:
    """Return (and create) a deterministic temp dir for a given case/report pair.
    IDs are sanitised to prevent path traversal. (REQ-C-19, REQ-C-21)"""
    safe = lambda s: "".join(c for c in s if c.isalnum() or c in "-_")[:64]
    d = pathlib.Path(tempfile.gettempdir()) / "nsight-render" / safe(case_id) / safe(report_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def orchestrate_render(
    case_id: str,
    report_id: str,
    material_id: str,
    client,
    *,
    view: str = "slides",
    out_dir: str | None = None,
) -> dict:
    """Load the report + the material's data, build the deck, convert to PDF, rasterize a preview.
    Returns {"pptx": <path>, "pdf": <path>, "preview": [<png paths>]}.
    (REQ-C-19, REQ-C-21, REQ-C-22)
    """
    # 1. Load and parse the report definition
    report = report_from_json(client.load_report(case_id, report_id))

    # 2. Fetch material bytes, write to temp .sav, ingest
    raw = client.get_material(material_id)
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name
    try:
        df, model = read_sav(tmp_path)
    finally:
        os.unlink(tmp_path)

    # Enrich model with multi-response + battery grouping
    model = enrich_model(model)

    # Guard (RX-be.3): a stacked single/multi chart needs a classifying variable
    # to define its segments. A BATTERY is exempt — its stack segments are the
    # shared rating-scale levels (no external classifier). Clean 422, not a crash.
    _STACKED = {"stacked_vertical_bar", "stacked_horizontal_bar"}
    for _chart in report.charts:
        if _chart.chart_type in _STACKED and not _chart.classifying_var:
            try:
                _is_battery = model.question(_chart.question_ref).kind == "battery"
            except Exception:
                _is_battery = False
            if not _is_battery:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Chart '{_chart.question_ref}' ({_chart.chart_type}): "
                        "Stacked charts need a classifying variable to define the segments"
                    ),
                )

    # 3. Build the PPTX deck into UNIQUE work files, then atomically publish to
    #    the canonical deck.pptx/deck.pdf names. Two concurrent renders of the
    #    SAME report never tear each other's output, and a GET preview.pdf in
    #    flight always reads a complete file (os.replace is atomic). (concurrency)
    out_dir = out_dir or tempfile.mkdtemp()
    uid = uuid.uuid4().hex[:8]
    work_pptx = os.path.join(str(out_dir), f"deck.{uid}.pptx")
    try:
        build_pptx(report, model, df, work_pptx)
    except ValueError as exc:
        # Surface chart-level errors (e.g. scatter with null scatter_xy) as a
        # clean 422 instead of an unhandled 500. (FIX-3)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # 4. Convert to PDF (requires LibreOffice soffice) — yields deck.<uid>.pdf
    work_pdf = pptx_to_pdf(work_pptx, str(out_dir))

    # 5. Atomically publish to the canonical names that the GET routes serve.
    final_pptx = os.path.join(str(out_dir), "deck.pptx")
    final_pdf = os.path.join(str(out_dir), "deck.pdf")
    os.replace(work_pptx, final_pptx)
    os.replace(work_pdf, final_pdf)

    # 6. Rasterize preview into a per-render subdir so concurrent renders don't
    #    mix each other's page*.png via the sorted glob.
    page_dir = os.path.join(str(out_dir), f"pages-{uid}")
    os.makedirs(page_dir, exist_ok=True)
    rasterize = slide_view if view != "pages" else page_view
    preview = rasterize(final_pdf, page_dir)

    # 7. Return artifact paths
    return {"pptx": final_pptx, "pdf": final_pdf, "preview": preview}


# ---------------------------------------------------------------------------
# Request body model
# ---------------------------------------------------------------------------


class RenderRequest(BaseModel):
    """Request body for POST .../render."""

    material_id: str
    view: str = "slides"


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@render_router.post("/cases/{case_id}/reports/{report_id}/render")
def render_report(
    case_id: str,
    report_id: str,
    body: RenderRequest,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Orchestrate PPTX build, PDF conversion, and preview rasterization for a report.
    Writes artifacts to a deterministic per-report dir so the preview PDF is fetchable.
    (REQ-C-19, REQ-C-21, REQ-C-22)"""
    out_dir = render_output_dir(case_id, report_id)
    result = orchestrate_render(
        case_id, report_id, body.material_id, client, view=body.view, out_dir=str(out_dir)
    )
    result["pdf_url"] = f"/cases/{case_id}/reports/{report_id}/preview.pdf"
    return result


@render_router.get("/cases/{case_id}/reports/{report_id}/preview.pdf")
def get_preview_pdf(case_id: str, report_id: str) -> FileResponse:
    """Stream the rendered PDF for a report to the client browser. (REQ-C-19, REQ-C-21)"""
    # pptx_to_pdf produces <stem>.pdf; since we write deck.pptx the output is deck.pdf
    pdf = render_output_dir(case_id, report_id) / "deck.pdf"
    if not pdf.exists():
        raise HTTPException(status_code=404, detail="not rendered yet")
    return FileResponse(str(pdf), media_type="application/pdf", filename="preview.pdf")


_PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@render_router.get("/cases/{case_id}/reports/{report_id}/preview.pptx")
def get_preview_pptx(case_id: str, report_id: str) -> FileResponse:
    """Stream the rendered PowerPoint deck for a report to the client browser.
    Returns 404 when the report has not been rendered yet."""
    pptx = render_output_dir(case_id, report_id) / "deck.pptx"
    if not pptx.exists():
        raise HTTPException(status_code=404, detail="not rendered yet")
    return FileResponse(str(pptx), media_type=_PPTX_MEDIA_TYPE, filename="preview.pptx")
