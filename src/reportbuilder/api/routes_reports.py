"""Reports routes: CRUD + duplicate under /cases/{case_id}/reports. (REQ-C-08..12)"""
from __future__ import annotations

import dataclasses
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.api.deps_auth import (current_session_id, require_case,
                                          require_case_write)
from reportbuilder.auth.permissions import User
from reportbuilder.store.repository import Repository
from reportbuilder.model.report import Report, report_from_json, report_to_json
from reportbuilder.store.datahive_client import DataHiveClient
from reportbuilder.store.seam import NotFound, StaleWrite


reports_router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _readable(report: Report) -> str:
    """Return the human-readable summary string for a report."""
    return (
        f"{report.name}: {len(report.charts)} charts ["
        + ",".join(c.chart_type for c in report.charts)
        + "]"
    )


def _canonicalize(body: dict) -> tuple[Report, str, str]:
    """Parse body → Report; return (report, report_json, readable).
    Raises HTTP 422 if the body is not a valid Report definition."""
    try:
        report = report_from_json(body)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid report definition: {exc}") from exc
    report_json = report_to_json(report)
    return report, report_json, _readable(report)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@reports_router.post("/cases/{case_id}/reports")
def create_report(
    case_id: str,
    body: dict = Body(...),
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
) -> dict:
    """Create a new report doc under a case. Returns the new report_id. (REQ-C-08, REQ-C-10, REQ-C-11)"""
    _refuse_until_sensitive_terms_accepted(client, case_id)
    _report, report_json, readable = _canonicalize(body)
    rid, version = client.save_report(case_id, None, report_json, readable)
    return {"report_id": rid, "version": version}


def _refuse_until_sensitive_terms_accepted(client, case_id: str) -> None:
    """No report until somebody has said which names must not reach a model.

    A report is the thing that generates headlines, themes and summaries, and
    every one of those sends the study's own wording to an LLM. The terms that
    must be pseudonymised first are proposed automatically from the study's
    structure, but a person has to confirm them — "Ahne" ("greedy") and
    "Validia" are both capitalised battery members and only a human tells the
    image attribute from the care provider.

    Gating REPORT CREATION rather than the LLM call is deliberate. It is one
    checkpoint, at the moment somebody is present and deciding, instead of a
    check on every code path that might one day reach a model — and a gate that
    depends on every future call site remembering is not a gate.

    Accepting an empty list is a valid answer and passes. Never having looked
    is what this refuses. A store that cannot answer does not block the app.
    """
    reader = getattr(client, "sensitive_terms", None)
    if reader is None:
        return
    materials = getattr(client, "list_materials", None)
    try:
        # Materialise inside the guard: a test double hands back a Mock, which
        # is truthy and not iterable, so deferring the list() to the loop threw
        # past this except and 500'd report creation.
        mats = list(materials(case_id) or []) if materials else []
    except Exception:  # noqa: BLE001 — a store that cannot answer must not
        return         # brick report creation
    for m in mats:
        # The listing keys this "material_id"; a bare "id" is the shape other
        # listings use. Reading only one of them made this gate silently find
        # no materials and let every report through.
        mid = (m.get("material_id") or m.get("id")) if isinstance(m, dict) \
            else getattr(m, "id", None)
        if not mid:
            continue
        try:
            if reader(mid).get("accepted") is not None:
                continue        # somebody reviewed this material already
            # Only refuse when there is something to review. A study whose
            # structure names no companies has nothing to show and nothing to
            # accept, and blocking it would be a gate on the fixture rather
            # than on the risk.
            #
            # The residual is deliberate and worth naming: a study that names
            # companies ONLY in free-text answers proposes nothing, so no gate
            # fires and nothing is registered. Structured studies — every one
            # seen so far — are covered; verbatims are not.
            from reportbuilder.api.model_loader import raw_model_for_material
            from reportbuilder.ingest.sensitive_terms import propose_sensitive_terms
            try:
                # Same source as the panel, deliberately: a gate that counted
                # different terms from the screen it points at would refuse
                # things the analyst had already dealt with — or, as here, let
                # everything through while the screen said it would not.
                proposed = propose_sensitive_terms(
                    raw_model_for_material(mid, client))
            except Exception:  # noqa: BLE001 — unreadable file proposes nothing
                proposed = []
            if proposed:
                raise HTTPException(
                    status_code=409,
                    detail=(f"{len(proposed)} possible company names were found "
                            "in this study and have not been reviewed yet. "
                            "Accept them on the case page before creating a "
                            "report — they are what gets pseudonymised before "
                            "any text reaches a model."),
                )
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — a store that cannot answer must not
            return        # brick report creation


def _base_version(request: Request) -> int | None:
    """The version an editor says it started from, from `If-Match`.

    A header rather than a field in the body: the report JSON round-trips
    through the model (report_from_json(report_to_json(r)) == r is an
    invariant), and threading a version through it would put a value in the
    document that is not part of the document. None when absent or unreadable —
    "no opinion", which is what every caller sent before this existed.
    """
    raw = (request.headers.get("if-match") or "").strip().strip('"')
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _refuse_if_locked_elsewhere(client, case_id: str, report_id: str, user: User,
                                doing: str) -> None:
    """409 unless this caller holds the report's editing lock.

    Every path that CHANGES a report goes through here. Guarding only the save
    left the others open, and the worst of them was deletion: while somebody
    had a report open and was working in it, anybody else could delete it out
    from under them — which is not a lost edit but a lost report.

    Reads and copies are not guarded: looking at a locked report, or taking a
    copy of it, harms nobody. Neither is generating its deck — that writes an
    artefact, not the report.
    """
    lock = client.report_lock(case_id, report_id)
    if lock and lock.get("user_id") != getattr(user, "id", ""):
        who = lock.get("user_name") or "Someone else"
        raise HTTPException(
            status_code=409,
            detail=f"{who} is editing this report, so it cannot be {doing}.")


@reports_router.get("/cases/{case_id}/reports")
def list_case_reports(
    case_id: str,
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case),
) -> dict:
    """List a case's reports — {"reports": [{report_id, name}]}.

    Server-side so reports are visible to any user/device, not just the creator's
    browser. (REQ-C-08)

    An unknown case_id lists empty rather than 404ing: a case a caller has never
    heard of and a case with nothing in it look the same from here, and the UI
    reads this before it knows which one it has.

    Each report also carries `rendering` — whether a render is in progress for
    it right now (server-side state; see routes_render.is_render_active) — so
    the list can show a report someone left mid-render as exactly that, not as
    stuck on whatever it was before.

    And who last edited it, when, and who has it open now. All of that comes
    from sidecars, so the whole page is ONE request: the case page used to
    fetch every report in full just to count its charts, which is what made it
    slow.
    """
    from reportbuilder.api.routes_render import is_render_active

    try:
        reports = client.list_reports(case_id)
    except (KeyError, NotFound):
        return {"reports": []}
    for r in reports:
        r["rendering"] = is_render_active(case_id, r["report_id"])
    return {"reports": reports}


@reports_router.put("/cases/{case_id}/reports/{report_id}")
def update_report(
    case_id: str,
    report_id: str,
    request: Request,
    body: dict = Body(...),
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
) -> dict:
    """Versioned-replace an EXISTING report doc. Returns the report_id. (REQ-C-08)

    A PUT must not resurrect a deleted report: if it no longer exists (e.g. a
    late save-on-unmount fires after the user deleted it) we return 404 instead
    of silently re-creating it."""
    try:
        client.load_report(case_id, report_id)
    except (KeyError, FileNotFoundError, NotFound) as exc:
        raise HTTPException(
            status_code=404, detail=f"Report '{report_id}' not found"
        ) from exc

    # Refuse a save from anyone but the person editing it.
    #
    # This is the check that actually prevents the loss; the lock icon in the
    # list only explains it. A save replaces the WHOLE document, so without
    # this a second editor does not merely conflict — their copy overwrites
    # everything the first person did, including slides they never opened, and
    # both saves return 200. Demonstrated against the running app before this
    # existed: two users edited different slides and one edit simply vanished.
    _refuse_if_locked_elsewhere(client, case_id, report_id, user, "saved")

    _report, report_json, readable = _canonicalize(body)
    # The version the editor started from, if it said. The lock is what
    # normally stops two people getting here at once, but it expires by design
    # — a crashed browser must not strand a report — so there is a window in
    # which one lapses, somebody else edits, and the first tab writes the
    # document it loaded hours ago over the top. That is a whole-document
    # replace: not a conflict to merge, a total loss of the other person's
    # work. An editor that sends nothing is not held to it, so older clients
    # and scripts keep working exactly as before.
    try:
        returned_id, version = client.save_report(
            case_id, report_id, report_json, readable,
            base_version=_base_version(request))
    except StaleWrite as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"report_id": returned_id, "version": version}


@reports_router.get("/cases/{case_id}/reports/{report_id}")
def get_report(
    case_id: str,
    report_id: str,
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case),
) -> dict:
    """Return the exact report definition JSON (parsed) for a report doc. (REQ-C-08)"""
    try:
        raw = client.load_report(case_id, report_id)
    except (KeyError, FileNotFoundError, NotFound) as exc:
        raise HTTPException(
            status_code=404, detail=f"Report '{report_id}' not found"
        ) from exc
    # The version rides in an ETag rather than in the body: the report JSON
    # round-trips through the model, and a version inside it would be a value
    # in the document that is not part of the document. The editor sends it
    # back as If-Match when it saves.
    version = 0
    reader = getattr(client, "report_version", None)
    if reader is not None:
        try:
            version = reader(case_id, report_id)
        except Exception:  # noqa: BLE001 — never fail a read over this
            version = 0
    return JSONResponse(json.loads(raw), headers={"ETag": f'"{version}"'})


@reports_router.delete("/cases/{case_id}/reports/{report_id}")
def delete_report(
    case_id: str,
    report_id: str,
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
) -> dict:
    """Delete a report doc. (REQ-C-12)

    Consent comes back as a 409 carrying the approval envelope, as for a case
    or a dataset — it used to escape as a bare 500, which left the UI with no
    approval link to offer.

    Refused while somebody else has it open. Deleting a report out from under
    an editor is not a lost edit, it is a lost report.
    """
    from reportbuilder.store.seam import ConsentRequired

    _refuse_if_locked_elsewhere(client, case_id, report_id, user, "deleted")

    # Asked here rather than inside the delete: a delete is re-run after
    # datahive grants consent, and by the second pass the objects removed on the
    # first are legitimately gone. Checking in there would turn the retry into a
    # 404.
    known = {r["report_id"] for r in client.list_reports(case_id)}
    if report_id not in known:
        raise HTTPException(
            status_code=404, detail=f"Report '{report_id}' not found")

    try:
        client.delete_report(case_id, report_id)
    except (KeyError, NotFound) as exc:
        raise HTTPException(
            status_code=404, detail=f"Report '{report_id}' not found") from exc
    except ConsentRequired as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "consent_required",
                "message": "Deleting needs approval in datahive.",
                "request_id": exc.request_id,
                "target": exc.target,
                "approve": exc.envelope.get("approval_urls", {}),
            },
        ) from exc
    return {"deleted": report_id}


class DuplicateBody(BaseModel):
    """Request body for POST .../duplicate."""
    name: str


@reports_router.post("/cases/{case_id}/reports/{report_id}/duplicate")
def duplicate_report(
    case_id: str,
    report_id: str,
    body: DuplicateBody,
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
) -> dict:
    """Duplicate a report under a new name; returns the new report_id. (REQ-C-09)

    Gated like creation, because it IS creation: the new report is what goes on
    to generate headlines and themes. Reports that predate the gate exist — in
    any store that was in use before it shipped — and duplicating one would
    have minted a fresh report with nobody having said which names must not
    reach a model.
    """
    _refuse_until_sensitive_terms_accepted(client, case_id)
    src = report_from_json(client.load_report(case_id, report_id))
    new_report: Report = dataclasses.replace(src, name=body.name)
    new_json = report_to_json(new_report)
    new_id, _version = client.save_report(case_id, None, new_json,
                                          _readable(new_report))
    return {"report_id": new_id}


@reports_router.post("/cases/{case_id}/reports/{report_id}/lock")
def lock_report(
    case_id: str,
    report_id: str,
    tab: str = "",
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
    session_id: str = Depends(current_session_id),
) -> dict:
    """Take the editing lock, or renew one already held.

    The editor calls this when it opens a report and every 30 seconds while it
    stays open. Renewal is the whole design: a browser that crashes, a laptop
    that closes and a network that drops all fail to run any release, so a lock
    that only cleared on request would strand the report. This one dies on its
    own about two minutes after the editor stops calling.

    200 with mine=true when it is yours. 409 when somebody else has it, naming
    them — refusing without saying who leaves the second person nothing to do
    but guess.
    """
    mine, lock = client.lock_report(case_id, report_id, tab_id=tab,
                                    session_id=session_id)
    if not mine:
        raise HTTPException(
            status_code=409,
            detail=f"{lock.get('user_name') or 'Someone else'} is editing this report.",
            headers={"X-Locked-By": lock.get("user_name", "")})
    return {"mine": True, **lock, "renew_seconds": Repository.LOCK_RENEW_SECONDS}


@reports_router.delete("/cases/{case_id}/reports/{report_id}/lock")
def unlock_report(
    case_id: str,
    report_id: str,
    tab: str = "",
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
) -> dict:
    """Give the lock back — closing the report, or leaving the page.

    Only the holder may. A lock anyone can drop is not a lock; one that was
    abandoned expires on its own rather than being tidied away by somebody who
    wants the report.

    `tab` identifies THIS editor. Closing one of your own tabs gives up that
    editor, not the report: another tab of yours may still be working in it, and
    taking the report away because you closed a different window is a lockout
    you inflicted on yourself.
    """
    return {"released": client.unlock_report(case_id, report_id, tab_id=tab)}
