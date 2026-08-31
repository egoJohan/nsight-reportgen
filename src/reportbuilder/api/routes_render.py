"""Render router: orchestrate the full export chain (REQ-C-19, REQ-C-21, REQ-C-22).

POST /cases/{case_id}/reports/{report_id}/render
  body: {"material_id": str}
  returns: {"pptx": <path>, "pdf": <path>, "pdf_url": <url>}

POST /cases/{case_id}/reports/{report_id}/render/cancel
  stops a render in progress for this report, between slides.

GET /cases/{case_id}/reports/{report_id}/render/status
  {"rendering": bool} -- whether a render is in progress for this report.
  Backed by server-side state, not client state, so it answers correctly
  for a browser that reloaded or never started the render itself.

GET /cases/{case_id}/reports/{report_id}/preview.pdf
  streams the rendered PDF (REQ-C-19, REQ-C-21)
"""
from __future__ import annotations

import asyncio
from reportbuilder import cache_dirs
import dataclasses
import logging
import pathlib
import tempfile
import os
import threading
import time
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.api.deps_auth import require_case, require_case_write
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import User
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext
from reportbuilder.export.pdf_convert import (
    pdf_page_count, pptx_to_pdf, pptx_to_pdf_parallel,
)
from reportbuilder.export.pptx_build import build_pptx
from reportbuilder.api.model_loader import df_model_for_material
from reportbuilder.model.report import report_from_json
from reportbuilder.render.deck import RenderCancelled
from reportbuilder.store.datahive_client import DataHiveClient

log = logging.getLogger(__name__)

render_router = APIRouter()


# ---------------------------------------------------------------------------
# Renders in progress (REQ: a render survives navigation/sign-out; an explicit
# Cancel is the only thing that stops it)
# ---------------------------------------------------------------------------
#
# One render per report at a time. Keyed in-process, not in datahive: this is
# where the mutex has to live anyway (the between-slides cancel flag is a
# threading.Event a worker thread polls), and it is naturally scoped to the
# process actually doing the work. Two renders of the SAME report racing to
# publish the SAME deck.pptx/deck.pdf is the failure mode worth avoiding, so a
# second POST while one is running is refused (409) rather than silently
# started alongside the first.
#
# This does not reach across processes: a multi-process deployment could still
# run two renders of one report concurrently, one per process. That is the
# same case orchestrate_render's unique-work-file + atomic os.replace publish
# was already written to survive (see its docstring) -- torn output is
# impossible either way, this registry just makes the common single-process
# case (a second click, a second tab) a clean 409 instead of a silent race.


@dataclasses.dataclass
class _ActiveRender:
    cancel: threading.Event


_active_renders: dict[tuple[str, str], _ActiveRender] = {}
_active_renders_lock = threading.Lock()


def is_render_active(case_id: str, report_id: str) -> bool:
    """Whether a render is in progress for this report right now.

    Used by the render-status route and by the reports list so a browser that
    reloaded mid-render -- or never started it -- can tell the difference
    between "not rendered" and "rendering".
    """
    with _active_renders_lock:
        return (case_id, report_id) in _active_renders


def active_renders_for_case(case_id: str) -> list[str]:
    """The reports of this case rendering right now, from memory.

    The case page shows a "Generating…" badge per report and kept it honest by
    re-fetching the whole report list every three seconds — one hive read per
    report plus one per lock, to answer a question this dict already holds. A
    thirty-second deck render cost roughly ten of those polls from a single
    browser that was only watching.
    """
    with _active_renders_lock:
        return sorted(rid for (cid, rid) in _active_renders if cid == case_id)


# ---------------------------------------------------------------------------
# Deterministic per-report output directory (REQ-C-19, REQ-C-21)
# ---------------------------------------------------------------------------


def render_output_dir(case_id: str, report_id: str) -> pathlib.Path:
    """Return (and create) a deterministic temp dir for a given case/report pair.
    IDs are sanitised to prevent path traversal. (REQ-C-19, REQ-C-21)"""
    safe = lambda s: "".join(c for c in s if c.isalnum() or c in "-_")[:64]
    d = cache_dirs.render_root() / safe(case_id) / safe(report_id)
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
    out_dir: str | None = None,
    cancel_check=None,
    template_path: str | None = None,
) -> dict:
    """Load the report + the material's data, build the deck, convert to PDF.
    Returns {"pptx": <path>, "pdf": <path>}. (REQ-C-19, REQ-C-21, REQ-C-22)

    No per-slide images. REQ-C-19b's slide-view/page-view toggle is two views of
    ONE artifact — the design said so — and that is how the app implements it:
    it fetches the PDF and lets the browser paginate. The chain rasterized a PNG
    per slide anyway, from the day it was written five days before the UI
    existed. Nothing ever fetched them (no route even served them), each render
    left another ~7 MB of them in /tmp, and /tmp is RAM.
    """
    # A render is something an analyst sits and waits through, so where the time
    # went is worth knowing without a profiler.
    marks: list[tuple[str, float]] = []
    started = time.monotonic()

    def mark(phase: str) -> None:
        marks.append((phase, time.monotonic() - started))

    # 1. Load and parse the report definition
    report = report_from_json(client.load_report(case_id, report_id))
    mark("report")

    # 2. Fetch material data + build the model with THIS report's grouping applied
    #    (auto-detection fills the gaps).
    df, model = df_model_for_material(material_id, client, report.grouping)
    mark("data")

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
        # The client's template, when one resolved. template_cache.resolve reads
        # its slots, fonts and type sizes — once per template, not once per
        # slide — and deck.py opens it as the base Presentation, so
        # the deck inherits the client's masters, theme and page size instead of
        # being a blank deck wearing nSight's colours.
        style = None
        if template_path:
            try:
                from reportbuilder.render.template_cache import resolve
                style = resolve(template_path).style
            except Exception:  # noqa: BLE001
                # An unreadable template must not fail the render; the deck
                # falls back to the generic style it used before templates.
                style = None
        mark("template")
        build_pptx(report, model, df, work_pptx, style=style,
                   cancel_check=cancel_check)
        mark("build")
    except ValueError as exc:
        # Surface chart-level errors (e.g. scatter with null scatter_xy) as a
        # clean 422 instead of an unhandled 500. (FIX-3)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Skip the expensive LibreOffice conversion if the client already cancelled.
    if cancel_check is not None and cancel_check():
        raise RenderCancelled()

    # 4. Convert to PDF (requires LibreOffice soffice) — yields deck.<uid>.pdf.
    #    A long deck is sliced and converted in parallel; a short one goes
    #    straight through, and anything unexpected falls back to one process.
    work_pdf = pptx_to_pdf_parallel(work_pptx, str(out_dir))
    mark("pdf")

    # 5. Atomically publish to the canonical names that the GET routes serve.
    final_pptx = os.path.join(str(out_dir), "deck.pptx")
    final_pdf = os.path.join(str(out_dir), "deck.pdf")
    os.replace(work_pptx, final_pptx)
    os.replace(work_pdf, final_pdf)

    last = 0.0
    parts = []
    for phase, at in marks:
        parts.append(f"{phase} {at - last:.1f}s")
        last = at
    log.info("rendered %s: %d slides in %.1fs (%s)", report_id,
             pdf_page_count(final_pdf), last, ", ".join(parts))

    # 6. Return artifact paths
    return {"pptx": final_pptx, "pdf": final_pdf}


def _font_warnings(repo: Repository, auth: AuthContext, case_id: str,
                   report_id: str) -> list[str]:
    """Reasons the resolved template's fonts are unavailable. Never raises.

    Read from what was recorded at upload rather than re-checked: this runs
    while someone waits for a deck, and a network round trip to Google Fonts
    does not belong on that path.
    """
    try:
        k = repo.find_case(auth, case_id)
        if k is None:
            return []
        template_id, _ = repo.resolve_template(auth, k.customer_id, k.id, report_id)
        if not template_id:
            return []
        for t in repo.list_templates(auth, k.customer_id):
            if t.id == template_id:
                return [f["reason"] for f in (t.fonts or [])
                        if isinstance(f, dict) and not f.get("ok")]
    except Exception:  # noqa: BLE001 — a warning must not fail a finished render
        return []
    return []


def _template_for(repo: Repository, auth: AuthContext, case_id: str,
                  report_id: str, out_dir: pathlib.Path) -> str | None:
    """Put the report's resolved template on disk and return its path.

    Resolution is report -> pinned -> tutkimus -> asiakas -> house default
    (Repository.resolve_template). Returns None when nothing is available, and
    the renderer falls back to a blank deck — a missing template is a styling
    problem, not a reason to fail a render the analyst is waiting on.

    Pins the resolved template onto the report, so changing the asiakas's
    template later restyles new reports and leaves this one as delivered.
    """
    k = repo.find_case(auth, case_id)
    if k is None:
        return None
    try:
        template_id, level = repo.resolve_template(auth, k.customer_id, k.id, report_id)
        blob = repo.template_bytes_for_report(auth, k.customer_id, k.id, report_id)
    except Exception:  # noqa: BLE001 — styling must not break rendering
        return None
    if not blob:
        return None

    path = out_dir / "template.pptx"
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    try:
        # Pin WITH its level, so a later, more specific choice can still win.
        repo.pin_template(auth, k.customer_id, k.id, report_id, template_id,
                          level=('customer' if level == 'pinned' else level))
    except Exception:  # noqa: BLE001
        pass
    return str(path)


def _persist_deck(repo: Repository, auth: AuthContext, case_id: str,
                  report_id: str, material_id: str, pptx_path: str) -> None:
    """Copy the finished deck into datahive so it outlives /tmp.

    The deck is the DELIVERABLE — the thing the analyst hands to a client — so
    it must not depend on a directory the OS is free to empty. The PDF and the
    page rasters are not copied: both derive from this file, so a wiped /tmp
    costs one LibreOffice conversion rather than a full re-render (fetch the
    .sav, re-parse, recompute every statistic, redraw every chart).

    Best-effort: a storage failure must not fail a render the user is watching.
    They still get their deck; it just is not cached.
    """
    k = repo.find_case(auth, case_id)
    if k is None:
        return
    try:
        key = repo.render_key(auth, k.customer_id, k.id, report_id, material_id)
        repo.save_render(auth, k.customer_id, k.id, report_id,
                         pathlib.Path(pptx_path).read_bytes(), key)
    except Exception:  # noqa: BLE001 — see docstring
        log = __import__("logging").getLogger(__name__)
        log.warning("could not persist deck for %s/%s", case_id, report_id,
                    exc_info=True)


def _restore_deck(repo: Repository, auth: AuthContext, case_id: str,
                  report_id: str, out_dir: pathlib.Path) -> bool:
    """Put a stored deck back on disk when /tmp no longer has it.

    Returns False when there is nothing usable — no stored deck, or one whose
    key no longer matches the report and material, in which case serving it
    would hand the user a deck that disagrees with its own data.
    """
    k = repo.find_case(auth, case_id)
    if k is None:
        return False
    materials = repo.list_materials(auth, k.customer_id, k.id)
    if not materials:
        return False
    try:
        key = repo.render_key(auth, k.customer_id, k.id, report_id, materials[0].id)
        blob = repo.load_render(auth, k.customer_id, k.id, report_id, key)
    except Exception:  # noqa: BLE001
        return False
    if not blob:
        return False
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "deck.pptx").write_bytes(blob)
    return True


# ---------------------------------------------------------------------------
# Request body model
# ---------------------------------------------------------------------------


class RenderRequest(BaseModel):
    """Request body for POST .../render."""

    material_id: str


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@render_router.post("/cases/{case_id}/reports/{report_id}/render")
async def render_report(
    case_id: str,
    report_id: str,
    body: RenderRequest,
    background: BackgroundTasks,
    client: DataHiveClient = Depends(get_client),
    auth: AuthContext = Depends(get_auth),
    repo: Repository = Depends(get_repository),
    user: User = Depends(require_case_write),
) -> dict:
    """Orchestrate the PPTX build and PDF conversion for a report.
    Writes artifacts to a deterministic per-report dir so the preview PDF is fetchable.

    Runs to completion regardless of the request: navigating away, closing the
    tab, or signing out does not stop it, and the deck still gets persisted to
    datahive. The only way to stop one is the explicit POST .../render/cancel,
    which sets the same between-slides cancel flag this used to get from a
    watched client disconnect -- the trigger changed, not the mechanism.
    (REQ-C-19, REQ-C-21, REQ-C-22)"""
    key = (case_id, report_id)
    with _active_renders_lock:
        if key in _active_renders:
            raise HTTPException(
                status_code=409,
                detail="A render for this report is already in progress",
            )
        cancel = threading.Event()
        _active_renders[key] = _ActiveRender(cancel=cancel)

    try:
        out_dir = render_output_dir(case_id, report_id)

        # Resolved before the render so the deck is built INTO the client's
        # template rather than styled afterwards.
        template_path = _template_for(repo, auth, case_id, report_id, out_dir)
        # Chart text uses the configured font, which is deliberately independent of
        # the template's: brand faces are often too wide for category labels.
        from reportbuilder.api.routes_settings import apply_chart_font
        apply_chart_font(repo, auth)

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: orchestrate_render(
                    case_id, report_id, body.material_id, client,
                    out_dir=str(out_dir), cancel_check=cancel.is_set,
                    template_path=template_path,
                ),
            )
        except RenderCancelled:
            # 499 = the render was told to stop (an explicit Cancel, not a
            # dropped connection -- the client that asked is usually still
            # right here waiting on this same response).
            raise HTTPException(status_code=499, detail="Render cancelled")
    finally:
        with _active_renders_lock:
            _active_renders.pop(key, None)

    # The deck outlives /tmp from here on. Done after the render rather than
    # inside it so a storage problem cannot cancel work the user just waited for
    # — and AFTER the response, because uploading a 2.5 MB deck to the store is
    # two more seconds of an analyst watching a spinner for a file that is
    # already on disk and already servable.
    background.add_task(_persist_deck, repo, auth, case_id, report_id,
                        body.material_id, result["pptx"])

    result["pdf_url"] = f"/cases/{case_id}/reports/{report_id}/preview.pdf"
    # A font the host cannot supply does not fail the render — LibreOffice
    # substitutes and the deck is usable — but the analyst is about to send it
    # to a client, so the deck's typeface being wrong has to be visible HERE
    # and not only on the template screen where it was uploaded.
    result["font_warnings"] = _font_warnings(repo, auth, case_id, report_id)
    return result


@render_router.post("/cases/{case_id}/reports/{report_id}/render/cancel")
def cancel_render(
    case_id: str,
    report_id: str,
    user: User = Depends(require_case_write),
) -> dict:
    """Stop a render in progress for this report, between slides.

    A write, not a read: cancelling someone else's render is an action, not a
    lookup, so this takes the same write guard the render itself does.

    Idempotent and never 404s: pressing Cancel a moment after the render
    already finished (or was cancelled once already) is a race the UI cannot
    fully avoid, and "nothing was running" is not an error -- the body says
    whether this call actually signalled a render, so the caller can tell.
    """
    with _active_renders_lock:
        active = _active_renders.get((case_id, report_id))
        if active is not None:
            active.cancel.set()
    return {"cancelled": active is not None}


@render_router.get("/cases/{case_id}/renders")
def case_renders(
    case_id: str,
    user: User = Depends(require_case),
) -> dict:
    """Report ids in this case with a render in progress.

    Deliberately NOT under /reports/... : a literal segment there would have to
    win against `/reports/{report_id}` on every router ordering, and a path
    that only works because of declaration order is a trap.
    """
    return {"rendering": active_renders_for_case(case_id)}


@render_router.get("/cases/{case_id}/reports/{report_id}/render/status")
def render_status(
    case_id: str,
    report_id: str,
    user: User = Depends(require_case),
) -> dict:
    """Whether a render is in progress for this report right now.

    Server-side state, not the caller's React state: a browser that reloaded
    mid-render, or opened the report for the first time while someone else's
    render is running, asks here rather than guessing from "not rendered yet".
    """
    return {"rendering": is_render_active(case_id, report_id)}


# Both artifacts live at a fixed URL and are rewritten by every render, so the
# browser must ask every time.
_NO_STORE = {"Cache-Control": "no-store, must-revalidate"}


@render_router.get("/cases/{case_id}/reports/{report_id}/preview.pdf")
def get_preview_pdf(case_id: str, report_id: str,
                    auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository),
                    user: User = Depends(require_case)) -> FileResponse:
    """Stream the rendered PDF for a report to the client browser. (REQ-C-19, REQ-C-21)

    Never cached. This URL is fixed but its content changes with every render,
    and with no Cache-Control the browser is free to reuse its copy on a
    heuristic — which is how a re-rendered deck kept showing the PREVIOUS
    render's slides and looked like the render had not taken effect.
    """
    # pptx_to_pdf produces <stem>.pdf; since we write deck.pptx the output is deck.pdf
    out = render_output_dir(case_id, report_id)
    pdf = out / "deck.pdf"
    if not pdf.exists():
        # Regenerate from the stored deck rather than giving up: the PDF is
        # derived, so a wiped /tmp should cost a conversion, not a re-render.
        if _restore_deck(repo, auth, case_id, report_id, out):
            pptx_to_pdf(str(out / "deck.pptx"), str(out))
            recovered = out / "deck.pdf"
            if recovered.exists():
                return FileResponse(str(recovered), media_type="application/pdf",
                                    filename="preview.pdf", headers=_NO_STORE)
        raise HTTPException(status_code=404, detail="not rendered yet")
    return FileResponse(str(pdf), media_type="application/pdf", filename="preview.pdf",
                        headers=_NO_STORE)


_PPTX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


@render_router.get("/cases/{case_id}/reports/{report_id}/preview.pptx")
def get_preview_pptx(case_id: str, report_id: str,
                     auth: AuthContext = Depends(get_auth),
                     repo: Repository = Depends(get_repository),
                     user: User = Depends(require_case)) -> FileResponse:
    """Stream the rendered PowerPoint deck for a report to the client browser.

    The deck is the deliverable, so /tmp is a cache and datahive is the record:
    if the local copy is gone, fetch the stored one back before giving up.

    Never cached, for the same reason as the PDF: same URL, new content on
    every render."""
    out = render_output_dir(case_id, report_id)
    pptx = out / "deck.pptx"
    if not pptx.exists() and not _restore_deck(repo, auth, case_id, report_id, out):
        raise HTTPException(status_code=404, detail="not rendered yet")
    return FileResponse(str(pptx), media_type=_PPTX_MEDIA_TYPE, filename="preview.pptx",
                        headers=_NO_STORE)
