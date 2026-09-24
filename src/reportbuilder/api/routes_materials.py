"""Materials routes: upload, list and delete a case's dataset. (REQ-C-01, REQ-C-04)"""
import logging
import os
import tempfile
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from reportbuilder.api.deps import get_client
from reportbuilder.api.deps_auth import (require_case, require_case_write,
                                         require_case_write_or_finish_delete)
from reportbuilder.api.deps_store import get_auth
from reportbuilder.api.routes_cases import _locks
from reportbuilder.store.seam import AuthContext
from reportbuilder.auth.permissions import User
from reportbuilder.ingest.sav_reader import read_sav, sav_file_label
from reportbuilder.store.datahive_client import DataHiveClient
from reportbuilder.store.seam import NotFound


log = logging.getLogger(__name__)

materials_router = APIRouter()


@materials_router.get("/cases/{case_id}/materials")
def list_case_materials(
    case_id: str,
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case),
) -> dict:
    """List the materials attached to a case — {"materials": [{material_id, name}]}.

    Server-side so any user/device opening the case sees its material(s), instead
    of relying on the uploader's browser-local state. (REQ-C-04)

    An unknown case_id lists empty rather than 404ing: a case a caller has never
    heard of and a case with nothing in it look the same from here, and the UI
    reads this before it knows which one it has.
    """
    try:
        return {"materials": client.list_materials(case_id)}
    except (KeyError, NotFound):
        return {"materials": []}


@materials_router.post("/cases/{case_id}/materials")
async def upload_material(
    case_id: str,
    file: UploadFile = File(...),
    client: DataHiveClient = Depends(get_client),
    user: User = Depends(require_case_write),
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
        try:
            df, model = read_sav(tmp_path)
            # The SAV's embedded study title (if any) — lets the UI name the case
            # from the file itself, falling back to the filename.
            file_label = sav_file_label(tmp_path)
        except Exception as exc:
            # A file we cannot read is the AUTHOR'S problem — wrong file, a
            # corrupt or truncated export — and saying so belongs where they are
            # standing. Letting it out as a 500 makes the web app declare a
            # service outage and cover the screen with the internal-error page,
            # which names neither the file nor the reason and offers a retry that
            # will fail identically. The traceback is logged for us; the author
            # gets the filename back.
            log.warning("upload: %s could not be read (%s: %s)",
                        file.filename, type(exc).__name__, exc, exc_info=True)
            raise HTTPException(
                status_code=422,
                detail=(f"{file.filename} could not be read as an SPSS .sav file. "
                        f"Check that the export completed and is not password "
                        f"protected, then try again."),
            ) from exc
    finally:
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
    user: User = Depends(require_case),
) -> dict:
    """What deleting this dataset would do, for the warning.

    `last_dataset` — the study becomes read-only; `remaining` — the files the
    reports use otherwise; `with_deck`/`without_deck` — the reports whose deck
    stays, and those that go entirely. Named, not counted: a list of reports is
    something an analyst can weigh before agreeing to it.
    """
    try:
        return client.dataset_usage(case_id, material_id)
    except (KeyError, NotFound):
        return {"last_dataset": False, "remaining": [], "with_deck": [], "without_deck": []}


@materials_router.delete("/cases/{case_id}/materials/{material_id}")
def delete_material(
    case_id: str,
    material_id: str,
    keep_decks: bool = True,
    client: DataHiveClient = Depends(get_client),
    auth: AuthContext = Depends(get_auth),
    user: User = Depends(require_case_write_or_finish_delete),
) -> dict:
    """Delete a dataset. The study's LAST dataset makes it read-only for good.

    Report definitions go with the data and the generated decks stay (spec
    docs/superpowers/specs/2026-09-24-dataset-deletion-design.md). One of
    several datasets goes on its own and the study stays live.

    Called again to FINISH a delete that was interrupted — by datahive asking
    for consent (a 409 carrying the approval envelope, as for a case), or by a
    process dying. The guard admits that call, and only that one, while the
    study is marked read-only but not yet completed.

    `keep_decks=false` — the warning's tick box left empty — deletes the decks
    and every report too. Recorded with the first call; a resumed delete keeps
    to it.
    """
    from reportbuilder.store.seam import ConsentRequired, NotFound

    state = client.dataset_deleted(case_id)
    finishing = bool(state) and not state.get("completed")
    if not finishing:
        # Asked here rather than inside the delete: a delete is re-run after
        # datahive grants consent, and by then objects removed on the first
        # pass are legitimately gone.
        known = {m["material_id"] for m in client.list_materials(case_id)}
        if material_id not in known:
            raise HTTPException(
                status_code=404, detail=f"Material '{material_id}' not found")
        # The same rule as deleting the study: somebody else's open report is
        # not taken from under them.
        held = {rid: lock for rid, lock in (_locks(client, case_id) or {}).items()
                if lock.get("user_id") != getattr(user, "id", "")}
        if held:
            names = sorted({(lock.get("user_name") or "Someone else")
                            for lock in held.values()})
            raise HTTPException(
                status_code=409,
                detail=(f"{' and '.join(names)} {'is' if len(names) == 1 else 'are'} "
                        f"editing {len(held)} of this study's reports, so its "
                        "dataset cannot be deleted yet."))

    try:
        result = client.delete_material(case_id, material_id, keep_decks=keep_decks)
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
    _forget_derived(case_id, material_id)
    if result.get("read_only"):
        _unregister_terms(client, auth, material_id)
    return {"deleted": material_id, "read_only": bool(result.get("read_only"))}


def _forget_derived(case_id: str, material_id: str) -> None:
    """What the server derived from the deleted data, outside the hive.

    Best-effort and idempotent: a cache left behind is served to nobody — a
    read-only study's decks come from the hive, not from `render_root` — so a
    failure here is logged, never raised."""
    import shutil

    from reportbuilder import cache_dirs
    try:
        from reportbuilder.api.routes_questions import clear_material_previews
        clear_material_previews(material_id)
    except Exception:  # noqa: BLE001
        log.info("could not clear the previews of %s", material_id, exc_info=True)
    try:
        shutil.rmtree(cache_dirs.render_root() / case_id, ignore_errors=True)
    except Exception:  # noqa: BLE001
        log.info("could not clear the deck cache of %s", case_id, exc_info=True)
    try:
        from reportbuilder.api.model_loader import forget_parsed
        forget_parsed(material_id)
    except Exception:  # noqa: BLE001
        log.info("could not forget the parsed data of %s", material_id, exc_info=True)


def _unregister_terms(client, auth: AuthContext, material_id: str) -> None:
    """Drop the deleted dataset's accepted terms from the tenant's masking list.

    Best-effort: if it fails, those terms stay masked — more masking, never
    less — until the next acceptance anywhere re-registers the union."""
    try:
        from reportbuilder.api.routes_questions import _register_with_datahive
        _register_with_datahive(auth, client.all_accepted_terms(exclude=material_id))
    except Exception:  # noqa: BLE001
        log.info("could not re-register masking terms after deleting %s",
                 material_id, exc_info=True)
