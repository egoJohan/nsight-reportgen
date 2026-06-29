"""Materials routes: POST /cases/{case_id}/materials (upload SAV + ingest). (REQ-C-01, REQ-C-04)"""
import tempfile
from fastapi import APIRouter, Depends, File, UploadFile

from reportbuilder.api.deps import get_client
from reportbuilder.ingest.sav_reader import read_sav, sav_file_label
from reportbuilder.store.datahive_client import DataHiveClient


materials_router = APIRouter()


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
