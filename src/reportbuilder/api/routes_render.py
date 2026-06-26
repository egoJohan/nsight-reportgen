"""Render router: orchestrate the full export chain (REQ-C-19, REQ-C-21, REQ-C-22).

POST /cases/{case_id}/reports/{report_id}/render
  body: {"material_id": str, "view"?: "slides"|"pages"}
  returns: {"pptx": <path>, "pdf": <path>, "preview": [<png paths>]}
"""
from __future__ import annotations

import tempfile
import os

from fastapi import APIRouter, Depends
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
    pptx = build_pptx(report, model, df, os.path.join(out_dir, "deck.pptx"))

    # 4. Convert to PDF (requires LibreOffice soffice)
    pdf = pptx_to_pdf(pptx, out_dir)

    # 5. Rasterize preview (slides view or pages view)
    rasterize = slide_view if view != "pages" else page_view
    preview = rasterize(pdf, out_dir)

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
    (REQ-C-19, REQ-C-21, REQ-C-22)"""
    return orchestrate_render(
        case_id, report_id, body.material_id, client, view=body.view
    )
