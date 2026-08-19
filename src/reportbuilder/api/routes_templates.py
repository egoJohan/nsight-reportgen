"""Presentation templates: upload, bind, resolve.

nSight's analysts render into their CLIENTS' brand decks, so a template is
validated on upload and rejected with a reason rather than silently producing a
deck that ignores it (render/template_check.py).

Binding follows the card: a template can be set on an asiakas, a tutkimus or a
single report, and the lower level always wins. An already-delivered report
keeps the template it rendered with until someone asks for the update — see
Repository.resolve_template.
"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.render.template_check import inspect_template
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, NotFound

templates_router = APIRouter()

_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class TemplateBinding(BaseModel):
    """None clears the binding, so the level above takes over again."""
    template_id: str | None = None


def _as_dict(t) -> dict:
    return {"id": t.id, "name": t.name, "size": t.size,
            "layout_name": t.layout_name, "palette": list(t.palette),
            "heading_font": t.heading_font}


@templates_router.post("/customers/{customer_id}/templates", status_code=201)
async def upload_template(customer_id: str, file: UploadFile = File(...),
                          auth: AuthContext = Depends(get_auth),
                          repo: Repository = Depends(get_repository)) -> dict:
    """Validate and store a template. 422 with the reason when it cannot work."""
    data = await file.read()
    if not data:
        raise HTTPException(422, "Empty file")

    # Validate from a temp copy: python-pptx needs a path, and a bad upload must
    # be rejected before anything is stored.
    import os
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name
    try:
        report = inspect_template(tmp_path)
    finally:
        os.unlink(tmp_path)

    if not report.ok:
        raise HTTPException(422, "; ".join(report.problems))

    best = report.best
    summary = {
        "layout_index": best.index if best else -1,
        "layout_name": best.name if best else "",
        "palette": report.theme.palette,
        "heading_font": report.theme.heading_font,
        "body_font": report.theme.body_font,
        "slide_width_in": report.slide_width_in,
        "slide_height_in": report.slide_height_in,
    }
    try:
        t = repo.upload_template(auth, customer_id, file.filename or "template.pptx",
                                 data, summary)
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    # Warnings that did not block the upload (e.g. no theme colours) are worth
    # showing: the deck will render, it just will not carry the client's brand.
    return {**_as_dict(t), "warnings": report.problems}


@templates_router.get("/customers/{customer_id}/templates")
def list_templates(customer_id: str, auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository)) -> list[dict]:
    return [_as_dict(t) for t in repo.list_templates(auth, customer_id)]


@templates_router.get("/customers/{customer_id}/templates/{template_id}/file")
def download_template(customer_id: str, template_id: str,
                      auth: AuthContext = Depends(get_auth),
                      repo: Repository = Depends(get_repository)) -> Response:
    try:
        return Response(repo.get_template_bytes(auth, customer_id, template_id),
                        media_type=_PPTX)
    except NotFound:
        raise HTTPException(404, f"Template '{template_id}' not found") from None


@templates_router.delete("/customers/{customer_id}/templates/{template_id}")
def delete_template(customer_id: str, template_id: str,
                    auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository)) -> dict:
    return {"removed": repo.delete_template(auth, customer_id, template_id)}


@templates_router.put("/customers/{customer_id}/template")
def bind_customer_template(customer_id: str, body: TemplateBinding,
                           auth: AuthContext = Depends(get_auth),
                           repo: Repository = Depends(get_repository)) -> dict:
    try:
        repo.set_template(auth, body.template_id, customer_id=customer_id)
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"customer_id": customer_id, "template_id": body.template_id}


@templates_router.put("/customers/{customer_id}/cases/{case_id}/template")
def bind_case_template(customer_id: str, case_id: str, body: TemplateBinding,
                       auth: AuthContext = Depends(get_auth),
                       repo: Repository = Depends(get_repository)) -> dict:
    try:
        repo.set_template(auth, body.template_id, customer_id=customer_id,
                          case_id=case_id)
    except NotFound:
        raise HTTPException(404, f"Case '{case_id}' not found") from None
    return {"case_id": case_id, "template_id": body.template_id}


@templates_router.put(
    "/customers/{customer_id}/cases/{case_id}/reports/{report_id}/template")
def bind_report_template(customer_id: str, case_id: str, report_id: str,
                         body: TemplateBinding,
                         auth: AuthContext = Depends(get_auth),
                         repo: Repository = Depends(get_repository)) -> dict:
    """Set (or clear) a template on a single report.

    A report's choice lives in its own definition rather than beside it, because
    template_ref is already part of the report model and the renderer reads it
    from there. Clearing it drops the report back to inheriting from its
    tutkimus, which is what a user who unsets an override expects.

    Also clears any pin: choosing a template deliberately is not the same as
    keeping the one a previous render happened to use.
    """
    import json as _json
    try:
        raw = repo.load_report(auth, customer_id, case_id, report_id)
    except NotFound:
        raise HTTPException(404, f"Report '{report_id}' not found") from None
    try:
        report = _json.loads(raw)
    except ValueError:
        raise HTTPException(422, "Report definition is not valid JSON") from None

    report["template_ref"] = body.template_id or ""
    repo.save_report(auth, customer_id, case_id,
                     _json.dumps(report, ensure_ascii=False), report_id=report_id)
    repo.clear_pinned_template(auth, customer_id, case_id, report_id)

    template_id, level = repo.resolve_template(auth, customer_id, case_id, report_id)
    return {"template_id": template_id, "level": level}


@templates_router.get(
    "/customers/{customer_id}/cases/{case_id}/reports/{report_id}/template")
def report_template(customer_id: str, case_id: str, report_id: str,
                    auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository)) -> dict:
    """What this report renders with, and WHERE that came from.

    The level is what lets the UI say "inherited from Attendo" rather than
    showing a bare id the user cannot act on.
    """
    template_id, level = repo.resolve_template(auth, customer_id, case_id, report_id)
    name = ""
    if template_id:
        name = next((t.name for t in repo.list_templates(auth, customer_id)
                     if t.id == template_id), "")
    return {"template_id": template_id, "level": level,
            "name": name or ("nSight-oletuspohja" if not template_id else template_id)}


@templates_router.post(
    "/customers/{customer_id}/cases/{case_id}/reports/{report_id}/template/refresh")
def refresh_report_template(customer_id: str, case_id: str, report_id: str,
                            auth: AuthContext = Depends(get_auth),
                            repo: Repository = Depends(get_repository)) -> dict:
    """The card's "päivitys pitää erikseen pyytää": move a delivered report onto
    whatever its tutkimus or asiakas now specifies."""
    repo.clear_pinned_template(auth, customer_id, case_id, report_id)
    template_id, level = repo.resolve_template(auth, customer_id, case_id, report_id)
    return {"template_id": template_id, "level": level}
