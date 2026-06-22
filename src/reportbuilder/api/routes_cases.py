"""Cases routes: POST /cases (create), GET /cases (list). (REQ-C-03, REQ-C-07)"""
from pydantic import BaseModel
from fastapi import APIRouter, Depends

from reportbuilder.api.deps import get_client
from reportbuilder.store.datahive_client import DataHiveClient


class CaseCreate(BaseModel):
    """Request body for POST /cases."""
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
