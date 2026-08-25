"""Presentation templates: upload, bind, resolve.

nSight's analysts render into their CLIENTS' brand decks, so a template is
validated on upload and rejected with a reason rather than silently producing a
deck that ignores it (render/template_check.py).

Binding follows the card: a template can be set on an asiakas, a tutkimus or a
single report, and the lower level always wins. An already-delivered report
keeps the template it rendered with until someone asks for the update — see
Repository.resolve_template.
"""
from dataclasses import replace

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from reportbuilder.api.deps_auth import (
    require_case, require_case_in_customer, require_case_in_customer_write,
    require_case_write, require_customer, require_customer_write,
)
from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.auth.permissions import User
from reportbuilder.render.template_check import inspect_template
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, NotFound

templates_router = APIRouter()

_PPTX = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


class TemplateBinding(BaseModel):
    """None clears the binding, so the level above takes over again."""
    template_id: str | None = None


def _as_dict(t) -> dict:
    d = {"id": t.id, "name": t.name, "size": t.size,
         "layout_name": t.layout_name, "palette": list(t.palette),
         "heading_font": t.heading_font}
    # Recorded at upload; carried on every listing so the UI can keep flagging a
    # template whose fonts the render host cannot supply.
    fonts = list(getattr(t, "fonts", ()) or ())
    d["fonts"] = fonts
    # No recorded check (a template uploaded before this existed) is not the
    # same as a failed one, so absence reads as OK rather than as an alarm.
    d["fonts_ok"] = all(f.get("ok") for f in fonts) if fonts else True
    return d


def _live_font_status(stored: list[dict], families: list[str]) -> list[dict]:
    """Re-check *families* against the host as it is RIGHT NOW.

    The stored record is what was true at upload. It cannot know about a font
    installed since, or a stand-in chosen a minute ago, so a template row would
    keep saying "Missing font" after the admin had already dealt with it.

    Where a font is still unresolved the STORED reason wins: it explains the
    licence ("not an open-licence font, cannot be installed"), while a
    network-free re-check can only say it is absent. Cheap enough for a list —
    no network, and fontconfig's family list is cached in-process.

    Re-checks every family we RECORDED as well as the ones the caller knows
    about. Callers pass the theme's heading/body pair, but the upload check
    reads every family the FILE names — a slide master routinely sets fonts the
    theme never mentions. Driving the result from the caller's list alone
    dropped those: the upload warned that "Barlow Condensed" could not be
    installed and the template's own row then did not list it, leaving an admin
    a warning about a font the product denied needing.
    """
    from reportbuilder.render.fonts import check_template_fonts

    by_family = {f.get("family"): f for f in stored if isinstance(f, dict)}
    wanted = list(families)
    wanted += [f for f in by_family if f and f not in wanted]
    try:
        live = check_template_fonts(wanted, allow_network=False)
    except Exception:  # noqa: BLE001 — fall back to what we recorded
        return stored
    out = []
    for st in live:
        if st.ok:
            out.append(st.as_dict())
        else:
            out.append(by_family.get(st.family) or st.as_dict())
    return out


def _resolve_template_fonts(theme, pptx_path: str = "") -> list[dict]:  # theme OR Template record
    """Install the fonts this template names, or record why we cannot.

    Done at UPLOAD, because that is when someone is looking and can act: get a
    licence, install the font, or choose a different template. Discovering it at
    render time means finding out after the deck was sent.

    Never raises: a template with an unavailable font still uploads and still
    renders — it just renders in a substitute, which is exactly what the
    returned status says out loud.
    """
    from reportbuilder.render.fonts import check_template_fonts, families_in_template
    # Every font the FILE names, not just the theme's major/minor pair. On
    # Egoiq_x_Rahoo the theme says Arial twice while the master sets the title in
    # Bebas Neue and the body in Barlow Condensed Medium — both open-licence
    # Google families nSight could have installed, and never learned it needed,
    # so the customer's headline rendered in a substitute.
    families = [f for f in (getattr(theme, "heading_font", ""),
                            getattr(theme, "body_font", "")) if f]
    if pptx_path:
        families += families_in_template(pptx_path)
    try:
        return [st.as_dict() for st in check_template_fonts(families)]
    except Exception:  # noqa: BLE001 — a font check must not block an upload
        return []


@templates_router.post("/customers/{customer_id}/templates", status_code=201)
async def upload_template(customer_id: str, file: UploadFile = File(...),
                          auth: AuthContext = Depends(get_auth),
                          repo: Repository = Depends(get_repository),
                          user: User = Depends(require_customer_write)) -> dict:
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
        # While the temp copy still exists: the font scan reads the FILE, and
        # this is the only moment it is on disk.
        font_status = _resolve_template_fonts(report.theme, tmp_path)
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
        "fonts": font_status,
    }
    try:
        t = repo.upload_template(auth, customer_id, file.filename or "template.pptx",
                                 data, summary)
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    # Warnings that did not block the upload (e.g. no theme colours) are worth
    # showing: the deck will render, it just will not carry the client's brand.
    # A font we cannot supply is not a reason to refuse the template. The .pptx
    # still NAMES the right font and looks correct on a machine that has it;
    # what degrades is the PDF and the previews, which are rasterised here.
    # Said plainly, because a warning that overstates its case gets ignored.
    font_problems = [f["reason"] for f in summary["fonts"] if not f["ok"]]
    return {**_as_dict(t), "warnings": report.problems + font_problems}


@templates_router.get("/customers/{customer_id}/templates")
def list_templates(customer_id: str, auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository),
                   user: User = Depends(require_customer)) -> list[dict]:
    """List a customer's templates, checking any whose fonts we never checked.

    The backfill is here rather than on the render path for two reasons: a
    template uploaded before the check existed would otherwise never be flagged,
    and this runs when someone opens the template panel — a place where a short
    pause is acceptable and a network round trip during a render is not. It
    happens once per template; the result is stored.
    """
    from reportbuilder.api.routes_settings import load_substitutions

    load_substitutions(repo, auth)
    out = []
    for t in repo.list_templates(auth, customer_id):
        if not t.fonts and t.heading_font:
            fonts = _resolve_template_fonts(t)
            if fonts:
                try:
                    repo.record_template_fonts(auth, customer_id, t.id, fonts)
                except Exception:  # noqa: BLE001 — a cache miss, not a failure
                    pass
                t = replace(t, fonts=tuple(fonts))
        # Re-checked against the host as it is now, so installing a font or
        # choosing a stand-in clears the row instead of leaving it stale.
        families = [f for f in (t.heading_font, t.body_font) if f]
        t = replace(t, fonts=tuple(_live_font_status(list(t.fonts), families)))
        out.append(_as_dict(t))
    return out


@templates_router.get("/customers/{customer_id}/templates/{template_id}")
def template_detail(customer_id: str, template_id: str,
                    auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository),
                    user: User = Depends(require_customer)) -> dict:
    """Everything known about one template, for the settings dialog.

    Font status is RE-RESOLVED rather than served from the stored record: a
    substitution chosen a minute ago has to show as resolved, and a font
    installed since the upload should stop being reported as missing.
    """
    from reportbuilder.api.routes_settings import load_substitutions
    from reportbuilder.render import fonts as F
    from reportbuilder.render import house_style as H

    for t in repo.list_templates(auth, customer_id):
        if t.id != template_id:
            continue
        load_substitutions(repo, auth)
        families = [f for f in (t.heading_font, t.body_font) if f]
        # allow_network=False: opening a dialog must not wait on Google Fonts.
        live = _live_font_status(list(t.fonts), families)
        return {**_as_dict(t), "body_font": t.body_font, "fonts": live,
                "fonts_ok": all(f["ok"] for f in live) if live else True,
                "available_fonts": H.available_chart_fonts()}
    raise HTTPException(404, f"Template '{template_id}' not found")


@templates_router.get("/customers/{customer_id}/templates/{template_id}/file")
def download_template(customer_id: str, template_id: str,
                      auth: AuthContext = Depends(get_auth),
                      repo: Repository = Depends(get_repository),
                      user: User = Depends(require_customer)) -> Response:
    try:
        return Response(repo.get_template_bytes(auth, customer_id, template_id),
                        media_type=_PPTX)
    except NotFound:
        raise HTTPException(404, f"Template '{template_id}' not found") from None


@templates_router.delete("/customers/{customer_id}/templates/{template_id}")
def delete_template(customer_id: str, template_id: str,
                    auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository),
                    user: User = Depends(require_customer_write)) -> dict:
    return {"removed": repo.delete_template(auth, customer_id, template_id)}


@templates_router.put("/customers/{customer_id}/template")
def bind_customer_template(customer_id: str, body: TemplateBinding,
                           auth: AuthContext = Depends(get_auth),
                           repo: Repository = Depends(get_repository),
                           user: User = Depends(require_customer_write)) -> dict:
    try:
        repo.set_template(auth, body.template_id, customer_id=customer_id)
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"customer_id": customer_id, "template_id": body.template_id}


@templates_router.put("/customers/{customer_id}/cases/{case_id}/template")
def bind_case_template(customer_id: str, case_id: str, body: TemplateBinding,
                       auth: AuthContext = Depends(get_auth),
                       repo: Repository = Depends(get_repository),
                       user: User = Depends(require_case_in_customer_write)) -> dict:
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
                         repo: Repository = Depends(get_repository),
                         user: User = Depends(require_case_in_customer_write)) -> dict:
    """Set (or clear) a template on a single report.

    A report's choice lives in its own definition rather than beside it, because
    template_ref is already part of the report model and the renderer reads it
    from there. Clearing it drops the report back to inheriting from its
    tutkimus, which is what a user who unsets an override expects.

    Also clears any pin: choosing a template deliberately is not the same as
    keeping the one a previous render happened to use.

    Refused while somebody else has the report open. This writes into the
    report's own definition, so it is a change to a document another person is
    editing — and it restyles every slide they are looking at.
    """
    import json as _json

    held = repo._lock_state(auth, customer_id, case_id, report_id)
    if held and held.get("user_id") != getattr(user, "id", ""):
        raise HTTPException(
            409,
            f"{held.get('user_name') or 'Someone else'} is editing this report, "
            f"so its template cannot be changed.")
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


@templates_router.get("/customers/{customer_id}/cases/{case_id}/template")
def case_template(customer_id: str, case_id: str,
                  auth: AuthContext = Depends(get_auth),
                  repo: Repository = Depends(get_repository),
                  user: User = Depends(require_case_in_customer)) -> dict:
    """What this tutkimus renders with, and where that came from."""
    template_id, level = repo.resolve_case_template(auth, customer_id, case_id)
    name = ""
    if template_id:
        name = next((t.name for t in repo.list_templates(auth, customer_id)
                     if t.id == template_id), "")
    return {"template_id": template_id, "level": level,
            "name": name or ("nSight default template" if not template_id else template_id)}


@templates_router.get(
    "/customers/{customer_id}/cases/{case_id}/reports/{report_id}/template")
def report_template(customer_id: str, case_id: str, report_id: str,
                    auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository),
                    user: User = Depends(require_case_in_customer)) -> dict:
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
            "name": name or ("nSight default template" if not template_id else template_id)}


@templates_router.post(
    "/customers/{customer_id}/cases/{case_id}/reports/{report_id}/template/refresh")
def refresh_report_template(customer_id: str, case_id: str, report_id: str,
                            auth: AuthContext = Depends(get_auth),
                            repo: Repository = Depends(get_repository),
                            user: User = Depends(require_case_in_customer_write)) -> dict:
    """The card's "päivitys pitää erikseen pyytää": move a delivered report onto
    whatever its tutkimus or asiakas now specifies."""
    repo.clear_pinned_template(auth, customer_id, case_id, report_id)
    template_id, level = repo.resolve_template(auth, customer_id, case_id, report_id)
    return {"template_id": template_id, "level": level}
