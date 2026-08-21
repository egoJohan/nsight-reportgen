"""Reports routes: CRUD + duplicate under /cases/{case_id}/reports. (REQ-C-08..12)"""
from __future__ import annotations

import dataclasses
import json

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.api.deps_auth import require_case, require_case_write
from reportbuilder.auth.permissions import User
from reportbuilder.model.report import Report, report_from_json, report_to_json
from reportbuilder.store.datahive_client import DataHiveClient
from reportbuilder.store.seam import NotFound


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
    _report, report_json, readable = _canonicalize(body)
    rid = client.save_report(case_id, None, report_json, readable)
    return {"report_id": rid}


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
    _report, report_json, readable = _canonicalize(body)
    returned_id = client.save_report(case_id, report_id, report_json, readable)
    return {"report_id": returned_id}


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
    return json.loads(raw)


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
    """
    from reportbuilder.store.seam import ConsentRequired

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
    """Duplicate a report under a new name; returns the new report_id. (REQ-C-09)"""
    src = report_from_json(client.load_report(case_id, report_id))
    new_report: Report = dataclasses.replace(src, name=body.name)
    new_json = report_to_json(new_report)
    new_id = client.save_report(case_id, None, new_json, _readable(new_report))
    return {"report_id": new_id}
