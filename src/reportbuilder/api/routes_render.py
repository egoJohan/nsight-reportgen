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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import page_view, slide_view
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.ingest.multi_group import apply_groups, suggest_multi_groups
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

    # Enrich model with multi-groups if any are detected
    groups = suggest_multi_groups(model)
    if groups:
        model = apply_groups(model, groups)

    # 3. Build the PPTX deck
    out_dir = out_dir or tempfile.mkdtemp()
    pptx = build_pptx(report, model, df, os.path.join(str(out_dir), "deck.pptx"))

    # 4. Convert to PDF (requires LibreOffice soffice)
    pdf = pptx_to_pdf(pptx, str(out_dir))

    # 5. Rasterize preview (slides view or pages view)
    rasterize = slide_view if view != "pages" else page_view
    preview = rasterize(pdf, str(out_dir))

    # 6. Return artifact paths
    return {"pptx": pptx, "pdf": pdf, "preview": preview}


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
