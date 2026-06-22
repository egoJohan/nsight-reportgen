"""Reports routes: CRUD + duplicate under /cases/{case_id}/reports. (REQ-C-08..12)"""
from __future__ import annotations

import dataclasses
import json

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from reportbuilder.api.deps import get_client
from reportbuilder.model.report import Report, report_from_json, report_to_json
from reportbuilder.store.datahive_client import DataHiveClient


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
) -> dict:
    """Create a new report doc under a case. Returns the new report_id. (REQ-C-08, REQ-C-10, REQ-C-11)"""
    _report, report_json, readable = _canonicalize(body)
    rid = client.save_report(case_id, None, report_json, readable)
    return {"report_id": rid}


@reports_router.put("/cases/{case_id}/reports/{report_id}")
def update_report(
    case_id: str,
    report_id: str,
    body: dict = Body(...),
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Versioned-replace an existing report doc. Returns the (possibly new) report_id. (REQ-C-08)"""
    _report, report_json, readable = _canonicalize(body)
    returned_id = client.save_report(case_id, report_id, report_json, readable)
    return {"report_id": returned_id}


@reports_router.get("/cases/{case_id}/reports/{report_id}")
def get_report(
    case_id: str,
    report_id: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Return the exact report definition JSON (parsed) for a report doc. (REQ-C-08)"""
    raw = client.load_report(report_id)
    return json.loads(raw)


@reports_router.delete("/cases/{case_id}/reports/{report_id}")
def delete_report(
    case_id: str,
    report_id: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Delete a report doc. (REQ-C-12)"""
    client.delete_report(report_id)
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
) -> dict:
    """Duplicate a report under a new name; returns the new report_id. (REQ-C-09)"""
    src = report_from_json(client.load_report(report_id))
    new_report: Report = dataclasses.replace(src, name=body.name)
    new_json = report_to_json(new_report)
    new_id = client.save_report(case_id, None, new_json, _readable(new_report))
    return {"report_id": new_id}
