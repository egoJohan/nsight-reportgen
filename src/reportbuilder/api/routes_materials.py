"""Materials routes: upload, list and delete a case's dataset. (REQ-C-01, REQ-C-04)"""
import tempfile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from reportbuilder.api.deps import get_client
from reportbuilder.ingest.sav_reader import read_sav, sav_file_label
from reportbuilder.store.datahive_client import DataHiveClient


materials_router = APIRouter()


@materials_router.get("/cases/{case_id}/materials")
def list_case_materials(
    case_id: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """List the materials attached to a case — {"materials": [{material_id, name}]}.

    Server-side so any user/device opening the case sees its material(s), instead
    of relying on the uploader's browser-local state. (REQ-C-04)
    """
    return {"materials": client.list_materials(case_id)}


@materials_router.post("/cases/{case_id}/materials")
async def upload_material(
    case_id: str,
    file: UploadFile = File(...),
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Upload a .sav file, ingest it, and attach it under a case. (REQ-C-01, REQ-C-04)

    Steps:
    1. Read uploaded bytes.
    2. Write to temp .sav file and call read_sav(tmp_path) -> (df, model).
    3. Build a deterministic codebook_summary from the model.
    4. Use the upload's filename as the material name.
    5. Call client.attach_material(case_id, name, raw_bytes, codebook_summary) -> material_id.
    6. Return {"material_id": material_id, "question_count": len(model.questions)}.
    """
    # 1. Read the uploaded bytes
    raw = await file.read()

    # 2. Write to temp file and call read_sav
    with tempfile.NamedTemporaryFile(suffix=".sav", delete=False) as tmp:
        tmp.write(raw)
        tmp_path = tmp.name

    try:
        df, model = read_sav(tmp_path)
        # The SAV's embedded study title (if any) — lets the UI name the case
        # from the file itself, falling back to the filename.
        file_label = sav_file_label(tmp_path)
    finally:
        # Clean up the temp file
        import os
        os.unlink(tmp_path)

    # 3. Build codebook_summary
    header = f"{len(model.questions)} questions, {len(model.variables)} variables"
    lines = [header]
    for q in model.questions:
        lines.append(f"{q.qid}\t{q.kind}\t{q.text}")
    codebook_summary = "\n".join(lines)

    # 4. Use filename as material name
    name = file.filename

    # 5. Call client.attach_material
    material_id = client.attach_material(case_id, name, raw, codebook_summary)

    # 6. Return response
    return {
        "material_id": material_id,
        "question_count": len(model.questions),
        "file_label": file_label,  # SAV study title, or null
    }


@materials_router.get("/cases/{case_id}/materials/{material_id}/usage")
def material_usage(
    case_id: str,
    material_id: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """What deleting this dataset would affect.

    Asked BEFORE the delete so the confirmation can name the reports rather than
    count them: "this empties Report 1, Report 2 and Report 3" is something an
    analyst can weigh, "3 reports affected" is not.
    """
    return {"reports": client.reports_using_material(case_id, material_id)}


@materials_router.delete("/cases/{case_id}/materials/{material_id}")
def delete_material(
    case_id: str,
    material_id: str,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """Delete a dataset and the curation and renders drawn from it.

    The tutkimus and its REPORTS survive: a report is an analyst's list of
    questions and how to chart them, and the usual reason to delete a dataset is
    to import a corrected export in its place. Throwing the layout away with the
    data would defeat that. The reports chart nothing until a dataset is
    imported again, which is what the confirmation warns about.

    Consent comes back as a 409 carrying the approval envelope, as for a case.
    """
    from reportbuilder.store.seam import ConsentRequired, NotFound

    # Asked here rather than inside the delete: a delete is re-run after
    # datahive grants consent, and by the second pass the objects removed on the
    # first are legitimately gone. Checking in there would turn the retry into a
    # 404.
    known = {m["material_id"] for m in client.list_materials(case_id)}
    if material_id not in known:
        raise HTTPException(
            status_code=404, detail=f"Material '{material_id}' not found")

    try:
        removed = client.delete_material(case_id, material_id)
    except (KeyError, NotFound) as exc:
        raise HTTPException(
            status_code=404, detail=f"Material '{material_id}' not found") from exc
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
    payload = {"deleted": material_id}
    if isinstance(removed, int):
        payload["objects_removed"] = removed
    return payload
