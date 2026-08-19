"""Settings: installing the fonts a customer's template needs.

Automatic resolution covers openly-licensed families only, and none of the real
customer templates use one — Attendo asks for Century Gothic and Calibri,
Synsam for Verdana, Holiday Club for Neue Haas Grotesk. Every one of them is
Monotype's or Microsoft's, so nSight will not fetch them (see render.fonts).

Without a way to install a font by hand, the only remaining route is a shell on
the render host and a copy into ~/.local/share/fonts. That is what this replaces.

Licence responsibility sits with whoever uploads. nSight declines to DOWNLOAD
commercial fonts because it cannot know the licence; an admin uploading a font
they hold a licence for is a different act, and the UI says so.
"""
from dataclasses import replace

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.render import fonts as F
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired, NotFound

settings_router = APIRouter(tags=["settings"])


def _font_dict(f, *, on_host: bool) -> dict:
    return {"id": f.id, "family": f.family, "filename": f.filename,
            "size": f.size, "on_host": on_host}


@settings_router.get("/settings/fonts")
def list_fonts(auth: AuthContext = Depends(get_auth),
               repo: Repository = Depends(get_repository)) -> dict:
    """Fonts installed by hand, plus which template families are still missing.

    `missing` is the actionable half: it names the families that uploaded
    templates ask for and this host cannot supply, so an admin knows what to
    upload instead of guessing from a deck that looks wrong.
    """
    stored = repo.list_fonts(auth)
    installed = F.installed_families(refresh=True)
    return {
        "fonts": [_font_dict(f, on_host=f.family.strip().lower() in installed)
                  for f in stored],
        "missing": _missing_families(repo, auth),
    }


def _missing_families(repo: Repository, auth: AuthContext) -> list[dict]:
    """Families every uploaded template names that this host cannot supply."""
    seen: dict[str, dict] = {}
    try:
        customers = repo.list_customers(auth)
    except Exception:  # noqa: BLE001 — settings must render even if a read fails
        return []
    for customer in customers:
        try:
            templates = repo.list_templates(auth, customer.id)
        except Exception:  # noqa: BLE001
            continue
        for t in templates:
            for entry in (t.fonts or ()):
                if not isinstance(entry, dict) or entry.get("ok"):
                    continue
                family = entry.get("family", "")
                row = seen.setdefault(family, {"family": family,
                                               "reason": entry.get("reason", ""),
                                               "templates": []})
                row["templates"].append(t.name)
    return sorted(seen.values(), key=lambda r: r["family"].lower())


@settings_router.post("/settings/fonts", status_code=201)
async def upload_font(file: UploadFile = File(...),
                      auth: AuthContext = Depends(get_auth),
                      repo: Repository = Depends(get_repository)) -> dict:
    """Install a .ttf/.otf on the render host and keep it in datahive.

    422 with the reason when the file is not a usable font — a WOFF renamed to
    .ttf is the likely mistake, and it would install without complaint and then
    silently fail to be used.
    """
    blob = await file.read()
    status = F.install_font_bytes(blob, filename=file.filename or "font.ttf")
    if not status.ok:
        raise HTTPException(422, status.reason)

    stored = repo.install_font(auth, file.filename or "font.ttf", blob,
                               status.family)
    return {**_font_dict(stored, on_host=True), "state": status.state}


@settings_router.delete("/settings/fonts/{font_id}")
def delete_font(font_id: str, auth: AuthContext = Depends(get_auth),
                repo: Repository = Depends(get_repository)) -> dict:
    """Remove a font from datahive and from this host."""
    try:
        family = repo.delete_font(auth, font_id)
    except NotFound:
        raise HTTPException(404, f"Font '{font_id}' not found") from None
    except ConsentRequired as exc:
        # datahive gates destructive operations. Surfaced with its approval
        # envelope rather than swallowed, so the caller can approve and retry
        # instead of seeing a delete that silently did nothing.
        raise HTTPException(409, {
            "error": "consent_required",
            "message": "Fontin poisto vaatii vahvistuksen datahivessä.",
            "request_id": exc.request_id,
            "target": exc.target,
            "approve": exc.envelope.get("approval_urls", {}),
        }) from exc
    removed = F.remove_font_file(family) if family else False
    return {"deleted": font_id, "family": family, "removed_from_host": removed}


def sync_fonts_to_host(repo: Repository, auth: AuthContext) -> list:
    """Materialise every stored font onto this host. Safe to call repeatedly."""
    return repo.sync_fonts(auth, F.install_font_bytes)


__all__ = ["settings_router", "sync_fonts_to_host", "replace"]
