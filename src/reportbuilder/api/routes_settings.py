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
import time

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from reportbuilder.api.deps_store import get_auth, get_repository
from reportbuilder.render import fonts as F
from reportbuilder.render import house_style as H
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, ConsentRequired, NotFound

settings_router = APIRouter(tags=["settings"])

CHART_FONT_KEY = "chart-font"
SUBSTITUTIONS_KEY = "font-substitutions"

# The setting is read on the render path, so it is cached briefly rather than
# fetched per chart. Short enough that a change takes effect while someone is
# still looking at the settings page, long enough that a six-slide deck does not
# make six round trips to datahive.
_CACHE_SECONDS = 20.0
_cached: tuple[float, str] | None = None


def chart_font_for(repo: Repository, auth: AuthContext) -> str:
    """The configured chart font family ("" = house default). Never raises."""
    global _cached
    now = time.monotonic()
    if _cached is not None and now - _cached[0] < _CACHE_SECONDS:
        return _cached[1]
    family = ""
    try:
        stored = repo.get_setting(auth, CHART_FONT_KEY) or {}
        family = (stored.get("family") or "").strip()
    except Exception:  # noqa: BLE001 — styling must not break a render
        family = _cached[1] if _cached else ""
    _cached = (now, family)
    return family


def apply_chart_font(repo: Repository, auth: AuthContext) -> str:
    """Make charts draw in the configured family. Returns what was applied."""
    return H.use_chart_font(chart_font_for(repo, auth))


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
    load_substitutions(repo, auth)
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


def load_substitutions(repo: Repository, auth: AuthContext) -> dict:
    """Stored substitutions, made active on this host. Never raises."""
    try:
        stored = repo.get_setting(auth, SUBSTITUTIONS_KEY) or {}
        mapping = {k: v for k, v in (stored.get("map") or {}).items()}
    except Exception:  # noqa: BLE001
        return F.substitutions()
    if mapping != F.substitutions():
        F.apply_substitutions(mapping)
    return mapping


@settings_router.get("/settings/font-substitutions")
def get_substitutions(auth: AuthContext = Depends(get_auth),
                      repo: Repository = Depends(get_repository)) -> dict:
    return {"map": load_substitutions(repo, auth),
            "available": H.available_chart_fonts()}


@settings_router.put("/settings/font-substitutions")
def put_substitutions(payload: dict = Body(...),
                      auth: AuthContext = Depends(get_auth),
                      repo: Repository = Depends(get_repository)) -> dict:
    """Choose stand-ins for fonts this host cannot supply.

    Render-side only: the .pptx keeps naming the real font, so a client who has
    it still sees their own brand. Only the PDF and the previews change.
    """
    mapping = payload.get("map") or {}
    if not isinstance(mapping, dict):
        raise HTTPException(422, "map must be an object")
    available = set(H.available_chart_fonts())
    for missing, use in mapping.items():
        if use and use not in available:
            raise HTTPException(
                422, f"The font '{use}' is not installed on this server.")
    applied = F.apply_substitutions(mapping)
    repo.set_setting(auth, SUBSTITUTIONS_KEY, {"map": applied})
    return {"map": applied}


@settings_router.get("/settings/chart-font")
def get_chart_font(auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository)) -> dict:
    """Which font charts draw in, and every family this host could use.

    Separate from the template's font on purpose: a brand display face is
    often wide, and chart text is mostly long category labels, so an admin may
    want a narrower one to fit more of a label before it is truncated.
    """
    family = chart_font_for(repo, auth)
    return {"family": family,
            "effective": H.use_chart_font(family),
            "default": H._DEFAULT_CHART_FONT,
            "available": H.available_chart_fonts()}


@settings_router.put("/settings/chart-font")
def set_chart_font(payload: dict = Body(...),
                   auth: AuthContext = Depends(get_auth),
                   repo: Repository = Depends(get_repository)) -> dict:
    """Set the chart font. An empty family restores the house default."""
    global _cached

    family = (payload.get("family") or "").strip()
    available = set(H.available_chart_fonts())
    if family and family not in available:
        raise HTTPException(
            422, f"The font '{family}' is not installed on this server.")
    repo.set_setting(auth, CHART_FONT_KEY, {"family": family})
    _cached = None                       # the next render must see the change
    return {"family": family, "effective": H.use_chart_font(family)}


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
            "message": "Deleting a font needs approval in datahive.",
            "request_id": exc.request_id,
            "target": exc.target,
            "approve": exc.envelope.get("approval_urls", {}),
        }) from exc
    removed = F.remove_font_file(family) if family else False
    return {"deleted": font_id, "family": family, "removed_from_host": removed}


def sync_fonts_to_host(repo: Repository, auth: AuthContext) -> list:
    """Materialise every stored font onto this host. Safe to call repeatedly."""
    return repo.sync_fonts(auth, F.install_font_bytes)


__all__ = ["settings_router", "sync_fonts_to_host", "apply_chart_font"]
