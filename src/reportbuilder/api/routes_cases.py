"""Cases routes: POST /cases (create), GET /cases (list), PATCH /cases/{id} (rename). (REQ-C-03, REQ-C-07)"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException

from reportbuilder.api.deps import get_client
from reportbuilder.store.datahive_client import DataHiveClient


class CaseCreate(BaseModel):
    """Request body for POST /cases."""
    name: str


class CaseRename(BaseModel):
    """Request body for PATCH /cases/{case_id}."""
    name: str


cases_router = APIRouter()


@cases_router.post("/cases")
def create_case(
    body: CaseCreate,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Create a case (project); return the new case_id. (REQ-C-03)"""
    case_id = client.create_case(body.name)
    return {"case_id": case_id}


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
    """Delete a case and its materials."""
    fn = getattr(client, "delete_case", None)
    if fn is None:
        raise HTTPException(status_code=501, detail="Delete not supported by this store")
    try:
        fn(case_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Case '{case_id}' not found") from exc
    return {"deleted": case_id}
