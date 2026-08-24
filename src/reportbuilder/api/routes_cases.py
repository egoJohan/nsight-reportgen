"""Cases routes: GET /cases (list), PATCH /cases/{id} (rename), DELETE /cases/{id}. (REQ-C-03, REQ-C-07)"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from reportbuilder.api.deps import get_client
from reportbuilder.api.deps_auth import current_user, require_case_write
from reportbuilder.auth.permissions import User
from reportbuilder.store.datahive_client import DataHiveClient


class CaseRename(BaseModel):
    """Request body for PATCH /cases/{case_id}."""
    name: str


cases_router = APIRouter()


@cases_router.post("/cases")
def create_case(user: User = Depends(current_user)) -> None:
    """Superseded: a tutkimus now lives under a customer, and this path carries
    none to put it in. `RepositoryClient` has no `create_case` — it cannot
    sensibly grow one — so this used to fail closed with a 500. 410 rather
    than 400 because the request isn't malformed, the endpoint is gone; the
    frontend already only calls the replacement (`grep '"/cases"'
    web/src/lib/api.ts` finds nothing)."""
    raise HTTPException(
        status_code=410,
        detail="POST /cases is gone. Create a case under its customer: "
               "POST /customers/{customer_id}/cases")


@cases_router.get("/cases")
def list_cases(
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(current_user),
) -> list[dict]:
    """List all cases (projects). (REQ-C-07)"""
    return client.list_cases()


@cases_router.patch("/cases/{case_id}")
def rename_case(
    case_id: str,
    body: CaseRename,
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
) -> dict:
    """Rename a case. Used to title a case from its SAV study label and for
    manual renames."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Case name cannot be empty")
    rename = getattr(client, "rename_case", None)
    if rename is None:
        raise HTTPException(status_code=501, detail="Rename not supported by this store")
    try:
        rename(case_id, name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found") from exc
    return {"id": case_id, "name": name}


def _locks(client, case_id: str) -> dict[str, dict]:
    """This case's live editing locks. A store that cannot answer (a legacy
    client, a test double) reports none rather than blocking a delete."""
    reader = getattr(client, "report_locks", None)
    if reader is None:
        return {}
    try:
        return reader(case_id) or {}
    except Exception:  # noqa: BLE001
        return {}


@cases_router.delete("/cases/{case_id}")
def delete_case(
    case_id: str,
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
) -> dict:
    """Delete a tutkimus and everything in it: materials, curation, reports, renders.

    datahive gates destructive operations behind explicit approval, so this can
    come back needing consent. That is returned as a 409 carrying the approval
    envelope rather than a bare error, so the caller can approve and retry —
    swallowing it would either do nothing or auto-approve destroying an
    analyst's work.
    """
    from reportbuilder.store.seam import ConsentRequired

    # Deleting the case deletes every report in it, so the guard that protects
    # one report has to protect all of them. Without this, the single-report
    # delete refused while somebody was editing — and the case delete took the
    # same report anyway, along with everything else, from a colleague who was
    # looking at it. A lost edit is recoverable; this is not.
    held = {rid: lock for rid, lock in (_locks(client, case_id) or {}).items()
            if lock.get("user_id") != getattr(user, "id", "")}
    if held:
        names = sorted({(lock.get("user_name") or "Someone else")
                        for lock in held.values()})
        who = " and ".join(names)
        raise HTTPException(
            status_code=409,
            detail=(f"{who} {'is' if len(names) == 1 else 'are'} editing "
                    f"{len(held)} of this study's reports, so it cannot be "
                    "deleted yet."))

    try:
        removed = client.delete_case(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found") from exc
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
    # Legacy stores return nothing from delete; only report a count we have.
    payload = {"deleted": case_id}
    if isinstance(removed, int):
        payload["objects_removed"] = removed
    return payload
