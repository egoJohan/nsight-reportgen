"""Cases routes: GET /cases (list), PATCH /cases/{id} (rename), DELETE /cases/{id}. (REQ-C-03, REQ-C-07)"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from reportbuilder.api.deps import get_client
from reportbuilder.store.datahive_client import DataHiveClient


class CaseRename(BaseModel):
    """Request body for PATCH /cases/{case_id}."""
    name: str


cases_router = APIRouter()


@cases_router.post("/cases")
def create_case() -> None:
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
) -> list[dict]:
    """List all cases (projects). (REQ-C-07)"""
    return client.list_cases()


@cases_router.patch("/cases/{case_id}")
def rename_case(
    case_id: str,
    body: CaseRename,
    client: DataHiveClient = Depends(get_client),
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


@cases_router.delete("/cases/{case_id}")
def delete_case(
    case_id: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Delete a tutkimus and everything in it: materials, curation, reports, renders.

    datahive gates destructive operations behind explicit approval, so this can
    come back needing consent. That is returned as a 409 carrying the approval
    envelope rather than a bare error, so the caller can approve and retry —
    swallowing it would either do nothing or auto-approve destroying an
    analyst's work.
    """
    from reportbuilder.store.seam import ConsentRequired

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
