"""Render router: orchestrate the full export chain (REQ-C-19, REQ-C-21, REQ-C-22).

POST /cases/{case_id}/reports/{report_id}/render
  body: {"material_id": str, "view"?: "slides"|"pages"}
  returns: {"pptx": <path>, "pdf": <path>, "preview": [<png paths>], "pdf_url": <url>}

GET /cases/{case_id}/reports/{report_id}/preview.pdf
  streams the rendered PDF (REQ-C-19, REQ-C-21)
"""
from __future__ import annotations

import asyncio
import pathlib
import tempfile
import os
import threading
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.export.pdf_convert import pptx_to_pdf
from reportbuilder.export.preview import page_view, slide_view
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.api.model_loader import df_model_for_material
from reportbuilder.model.report import report_from_json
from reportbuilder.render.deck import RenderCancelled
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
    cancel_check=None,
) -> dict:
    """Load the report + the material's data, build the deck, convert to PDF, rasterize a preview.
    Returns {"pptx": <path>, "pdf": <path>, "preview": [<png paths>]}.
    (REQ-C-19, REQ-C-21, REQ-C-22)
    """
    # 1. Load and parse the report definition
    report = report_from_json(client.load_report(case_id, report_id))

    # 2. Fetch material data + build the model with THIS report's grouping applied
    #    (auto-detection fills the gaps).
    df, model = df_model_for_material(material_id, client, report.grouping)

    # A stacked chart with no classifying variable is a valid single 100%-stacked
    # distribution bar (the "total-only" case) — it renders the answer categories
    # as the stack. No guard needed here.

    # 3. Build the PPTX deck into UNIQUE work files, then atomically publish to
    #    the canonical deck.pptx/deck.pdf names. Two concurrent renders of the
    #    SAME report never tear each other's output, and a GET preview.pdf in
    #    flight always reads a complete file (os.replace is atomic). (concurrency)
    out_dir = out_dir or tempfile.mkdtemp()
    uid = uuid.uuid4().hex[:8]
    work_pptx = os.path.join(str(out_dir), f"deck.{uid}.pptx")
    try:
        build_pptx(report, model, df, work_pptx, cancel_check=cancel_check)
    except ValueError as exc:
        # Surface chart-level errors (e.g. scatter with null scatter_xy) as a
        # clean 422 instead of an unhandled 500. (FIX-3)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Skip the expensive LibreOffice conversion if the client already cancelled.
    if cancel_check is not None and cancel_check():
        raise RenderCancelled()

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
async def render_report(
    case_id: str,
    report_id: str,
    body: RenderRequest,
    request: Request,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Orchestrate PPTX build, PDF conversion, and preview rasterization for a report.
    Writes artifacts to a deterministic per-report dir so the preview PDF is fetchable.

    Cancellable: the heavy build runs in a worker thread while we watch for the client
    aborting the request; on disconnect a cancel flag is set and the render stops
    promptly (between slides), so a mistakenly-started 170-slide run doesn't grind on.
    (REQ-C-19, REQ-C-21, REQ-C-22)"""
    out_dir = render_output_dir(case_id, report_id)
    cancel = threading.Event()

    async def _watch_disconnect():
        try:
            while not cancel.is_set():
                if await request.is_disconnected():
                    cancel.set()
                    return
                await asyncio.sleep(0.4)
        except asyncio.CancelledError:
            pass

    watcher = asyncio.create_task(_watch_disconnect())
    try:
        result = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: orchestrate_render(
                case_id, report_id, body.material_id, client,
                view=body.view, out_dir=str(out_dir), cancel_check=cancel.is_set,
            ),
        )
    except RenderCancelled:
        # 499 = client closed request (the browser already aborted; body is moot).
        raise HTTPException(status_code=499, detail="Render cancelled")
    finally:
        cancel.set()
        watcher.cancel()

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
