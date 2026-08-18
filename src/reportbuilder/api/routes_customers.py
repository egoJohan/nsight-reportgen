"""Asiakas and Case routes — nSight's OWN API, served to nSight's web app.

Nothing here reaches datahive directly: these call the Repository, which calls
the four-method seam, which speaks only generic `/api/v1/objects`. Datahive
never learns what an asiakas is (floor rule 6).

Trello: Asiakkuuden hallinta. Speksi 2 P-O-01. Additive — the existing
`/cases/*` surface is untouched while the UI moves over.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, NotFound

customers_router = APIRouter()


class NameBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def _name(body: NameBody) -> str:
    name = body.name.strip()
    if not name:
        raise HTTPException(422, "Name cannot be empty")
    return name


@customers_router.post("/customers", status_code=201)
def create_customer(body: NameBody, auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository)) -> dict:
    c = repo.create_customer(auth, _name(body))
    return {"id": c.id, "name": c.name}


@customers_router.get("/customers")
def list_customers(auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository)) -> list[dict]:
    """Only the customers this caller may see — datahive filters the listing,
    so an over-permissive UI cannot widen it."""
    return [{"id": c.id, "name": c.name} for c in repo.list_customers(auth)]


@customers_router.get("/customers/{customer_id}")
def get_customer(customer_id: str, auth: AuthContext = Depends(get_auth),
                 repo: Repository = Depends(get_repository)) -> dict:
    try:
        c = repo.get_customer(auth, customer_id)
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"id": c.id, "name": c.name}


@customers_router.patch("/customers/{customer_id}")
def rename_customer(customer_id: str, body: NameBody,
                    auth: AuthContext = Depends(get_auth),
                    repo: Repository = Depends(get_repository)) -> dict:
    try:
        c = repo.rename_customer(auth, customer_id, _name(body))
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"id": c.id, "name": c.name}


@customers_router.post("/customers/{customer_id}/cases", status_code=201)
def create_case(customer_id: str, body: NameBody,
                auth: AuthContext = Depends(get_auth),
                repo: Repository = Depends(get_repository)) -> dict:
    try:
        k = repo.create_case(auth, customer_id, _name(body))
    except NotFound:
        raise HTTPException(404, f"Customer '{customer_id}' not found") from None
    return {"id": k.id, "customer_id": k.customer_id, "name": k.name}


@customers_router.get("/customers/{customer_id}/cases")
def list_cases(customer_id: str, auth: AuthContext = Depends(get_auth),
               repo: Repository = Depends(get_repository)) -> list[dict]:
    return [{"id": k.id, "customer_id": k.customer_id, "name": k.name}
            for k in repo.list_cases(auth, customer_id)]


@customers_router.get("/customers/{customer_id}/cases/{case_id}")
def get_case(customer_id: str, case_id: str, auth: AuthContext = Depends(get_auth),
             repo: Repository = Depends(get_repository)) -> dict:
    try:
        k = repo.get_case(auth, customer_id, case_id)
    except NotFound:
        raise HTTPException(404, f"Case '{case_id}' not found") from None
    return {"id": k.id, "customer_id": k.customer_id, "name": k.name}


@customers_router.patch("/customers/{customer_id}/cases/{case_id}")
def rename_case(customer_id: str, case_id: str, body: NameBody,
                auth: AuthContext = Depends(get_auth),
                repo: Repository = Depends(get_repository)) -> dict:
    try:
        k = repo.rename_case(auth, customer_id, case_id, _name(body))
    except NotFound:
        raise HTTPException(404, f"Case '{case_id}' not found") from None
    return {"id": k.id, "customer_id": k.customer_id, "name": k.name}


@customers_router.get("/reports/recent")
def recent_reports(limit: int = Query(default=10, ge=1, le=50),
                   auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository)) -> list[dict]:
    """The caller's most recently modified reports, newest first.

    "Accessible to this person" is the store's answer, not a filter applied
    here: the underlying listing only returns paths this caller may read.
    """
    return [
        {"id": r.id, "case_id": r.case_id, "customer_id": r.customer_id,
         "name": r.name, "modified_at": r.modified_at}
        for r in repo.recent_reports(auth, limit=limit)
    ]


@customers_router.get("/cases/{case_id}/resolve")
def resolve_case(case_id: str, auth: AuthContext = Depends(get_auth),
                 repo: Repository = Depends(get_repository)) -> dict:
    """Resolve a bare case id to its case and owning customer.

    The UI holds case ids in URLs that predate the hierarchy, so it needs a way
    to ask "which customer does this belong to, and what is it called?" without
    already knowing the answer.
    """
    k = repo.find_case(auth, case_id)
    if k is None:
        raise HTTPException(404, f"Case '{case_id}' not found")
    customer_name = ""
    try:
        customer_name = repo.get_customer(auth, k.customer_id).name
    except NotFound:
        pass
    return {"id": k.id, "name": k.name, "customer_id": k.customer_id,
            "customer_name": customer_name}
