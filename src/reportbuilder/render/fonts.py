"""Make a template's fonts real, or say plainly that we cannot.

A PowerPoint template only NAMES its fonts; it does not carry them. When the
render host lacks one, nothing fails — fontconfig quietly substitutes, LibreOffice
draws the deck in Noto Sans, and the output looks subtly unlike the customer's
brand with no indication why. That silence is the problem this module removes.

Resolution order for a family:

1. Already installed on the host -> use it.
2. Served by Google Fonts under an OPEN licence -> download and install it.
3. Anything else -> UNAVAILABLE, with a reason the user can act on.

Step 3 is deliberately not a substitution. Swapping in a look-alike is how the
current silent fallback misleads people; an explicit "this template asks for
Century Gothic and we cannot supply it" lets someone install the font, get a
licence, or pick another template.

Licence matters and is checked, not assumed. The CSS API happily serves Century
Gothic, Verdana and Calibri, but those files carry "licensed to Google Inc." and
remain Monotype's or Microsoft's property: Google may serve them to web pages;
we may not install them on a render host and embed them in customer decks.

The licence is read from the Google Fonts library metadata
(fonts.google.com/metadata/fonts, ~1900 families, no API key), which lists only
the open-licence library and flags each entry with `isOpenSource`. A family
absent from it — Century Gothic, Calibri, Verdana, Neue Haas Grotesk — is not
ours to install.

The gstatic URL shape is NOT a licence signal, though it looks like one: the
same family comes back as `/s/questrial/....ttf` or `/l/font?kit=...` depending
on the request's User-Agent, so OFL-licensed Questrial can arrive on the same
URL shape as commercial Century Gothic.
"""
from __future__ import annotations

import os
import pathlib
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass

# Where downloaded fonts land. Its own directory, so what nSight installed stays
# separable from what the machine already had.
FONT_DIR = pathlib.Path(
    os.environ.get("NSIGHT_FONT_DIR", "~/.local/share/fonts/nsight")
).expanduser()

_CSS_URL = "https://fonts.googleapis.com/css?family={family}"
# The open-licence library. Its response is prefixed with an XSSI guard, so the
# body is parsed from its first "{" rather than handed straight to json.loads.
_METADATA_URL = "https://fonts.google.com/metadata/fonts"
# The CSS API picks the file format from the User-Agent, and only one of the old
# ones yields something fontconfig can use. Measured against Questrial:
#   "Mozilla/4.0"                       -> .ttf   <- what we need
#   "Mozilla/4.0 (compatible; MSIE 6.0)" -> EOT   (fontconfig ignores it)
#   old Safari / Firefox 3.6            -> .woff  (fontconfig ignores it)
# A bare Mozilla/4.0 it is. The bytes are checked after download anyway, since
# a UA is a request, not a guarantee.
_LEGACY_UA = "Mozilla/4.0"

# sfnt magic numbers: TrueType, the Apple variant, CFF/OpenType, collections.
_SFNT_MAGIC = (b"\x00\x01\x00\x00", b"true", b"OTTO", b"ttcf")
_TIMEOUT = 8.0

PRESENT = "present"           # the host already had it
INSTALLED = "installed"       # we fetched it and installed it just now
UNAVAILABLE = "unavailable"   # we cannot supply it — say so


@dataclass(frozen=True)
class FontStatus:
    """What happened when we tried to make *family* usable."""

    family: str
    state: str
    source: str = ""     # "system" | "google-fonts" | "upload"
    reason: str = ""     # populated only when UNAVAILABLE

    @property
    def ok(self) -> bool:
        return self.state in (PRESENT, INSTALLED)

    def as_dict(self) -> dict:
        return {"family": self.family, "state": self.state,
                "source": self.source, "reason": self.reason, "ok": self.ok}


# --- what the host already has ---------------------------------------------

_installed_cache: set[str] | None = None


def installed_families(*, refresh: bool = False) -> set[str]:
    """Lower-cased family names fontconfig knows about.

    fc-LIST, not fc-match: fc-match always succeeds — ask it for Century Gothic
    on a machine without it and it returns Noto Sans, which is precisely the
    substitution we are trying to detect.
    """
    global _installed_cache
    if _installed_cache is not None and not refresh:
        return _installed_cache
    families: set[str] = set()
    try:
        out = subprocess.run(["fc-list", ":", "family"], capture_output=True,
                             text=True, timeout=20, check=False).stdout
    except (OSError, subprocess.SubprocessError):
        out = ""
    for line in out.splitlines():
        # One line per face: "Noto Sans,Noto Sans Regular" — every alias counts.
        for name in line.split(","):
            name = name.strip()
            if name:
                families.add(name.lower())
    _installed_cache = families
    return families


def is_installed(family: str) -> bool:
    return bool(family) and family.strip().lower() in installed_families()


# --- fetching from Google Fonts --------------------------------------------

def _fetch(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": _LEGACY_UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
        return resp.read()


_library_cache: dict[str, bool] | None = None


def open_library(*, timeout: float = _TIMEOUT, fetch=None,
                 refresh: bool = False) -> dict[str, bool]:
    """Lower-cased family -> isOpenSource, for the Google Fonts open library.

    An empty dict means the listing could not be read. Callers treat that as
    "cannot confirm the licence" and refuse to install, rather than assuming
    the permissive answer.
    """
    global _library_cache
    if _library_cache is not None and not refresh:
        return _library_cache
    import json

    fetch = fetch or _fetch
    try:
        raw = fetch(_METADATA_URL, timeout).decode("utf-8", "replace")
        data = json.loads(raw[raw.index("{"):])
    except (urllib.error.URLError, OSError, TimeoutError, ValueError):
        return {}
    out = {}
    for entry in data.get("familyMetadataList", []):
        name = (entry.get("family") or "").strip().lower()
        if name:
            out[name] = bool(entry.get("isOpenSource", False))
    if out:
        _library_cache = out
    return out


def google_font_url(family: str, *, timeout: float = _TIMEOUT,
                    fetch=None) -> tuple[str | None, str]:
    """(download_url, reason). url is None when we must not or cannot fetch.

    Returns the reason instead of raising, because every failure here is
    something the user needs told, not an exception to swallow.
    """
    fetch = fetch or _fetch
    # Licence first: never fetch a font file we would not be allowed to keep.
    library = open_library(timeout=timeout, fetch=fetch)
    key = family.strip().lower()
    if not library:
        return None, ("Fonttikirjaston lisenssitietoja ei saatu haettua, "
                      f"joten fonttia '{family}' ei asenneta.")
    if key not in library:
        return None, (f"'{family}' ei ole avoimen lisenssin fontti (esim. "
                      "Monotypen tai Microsoftin fontti). Sitä ei voi asentaa "
                      "palvelimelle automaattisesti. Asenna fontti lisenssin "
                      "kanssa palvelimelle tai käytä toista pohjaa.")
    if not library[key]:
        return None, (f"'{family}' on Google Fontsissa, mutta ei avoimella "
                      "lisenssillä, joten sitä ei voi asentaa palvelimelle.")

    quoted = family.strip().replace(" ", "+")
    try:
        body = fetch(_CSS_URL.format(family=quoted), timeout).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            return None, f"Google Fonts ei tunne fonttia '{family}'."
        return None, f"Google Fonts vastasi virheellä {exc.code}."
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return None, f"Google Fontsiin ei saatu yhteyttä ({exc.__class__.__name__})."

    if "@font-face" not in body:
        return None, f"Google Fonts ei tarjoa fonttia '{family}'."
    # Prefer an explicitly TrueType source when the CSS offers several.
    truetype = re.search(r"url\((https://[^)]+)\)\s*format\('truetype'\)", body)
    m = truetype or re.search(r"url\((https://[^)]+)\)", body)
    if not m:
        return None, f"Google Fontsin vastauksesta ei löytynyt tiedostoa fontille '{family}'."
    # Both /s/<family>/<hash>.ttf and /l/font?kit=... are returned for open
    # families depending on the User-Agent; by here the licence is settled, so
    # whichever URL the API gave is the one to fetch.
    return m.group(1), ""


def _refresh_font_cache() -> None:
    try:
        subprocess.run(["fc-cache", "-f", str(FONT_DIR)],
                       capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def family_of(blob: bytes) -> str:
    """The family name recorded INSIDE a font file, or "".

    Read from the font rather than taken from the filename, which is whatever
    someone typed: "brand-font-FINAL-v2.ttf" says nothing about what fontconfig
    will call the family, and the name is what a template asks for.
    """
    import io

    try:
        from fontTools.ttLib import TTFont
    except ImportError:
        return ""
    try:
        font = TTFont(io.BytesIO(blob), lazy=True, fontNumber=0)
        names = font["name"]
        # 16 = typographic family, the one that matches what PowerPoint records
        # for families with more than four styles; 1 = legacy family.
        for name_id in (16, 1):
            rec = names.getDebugName(name_id)
            if rec:
                return rec.strip()
    except Exception:  # noqa: BLE001 — a broken upload is a message, not a crash
        return ""
    return ""


def install_font_bytes(blob: bytes, *, filename: str = "font.ttf",
                       family: str = "") -> FontStatus:
    """Install a font FILE on this host. Shared by upload and cloud download.

    Verifies through fontconfig rather than trusting the write: a file on disk
    that fontconfig does not report is a font that will still be substituted at
    render time, and reporting success there would restore the silence.
    """
    if not blob:
        return FontStatus(family or filename, UNAVAILABLE,
                          reason="Tiedosto on tyhjä.")
    if not blob.startswith(_SFNT_MAGIC):
        return FontStatus(
            family or filename, UNAVAILABLE,
            reason="Tiedosto ei ole .ttf- tai .otf-fontti. Verkkofontteja "
                   "(WOFF, WOFF2, EOT) ei voi asentaa palvelimelle.")

    detected = family or family_of(blob)
    if not detected:
        return FontStatus(filename, UNAVAILABLE,
                          reason="Fontin nimeä ei saatu luettua tiedostosta.")

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9]+", "-", detected).strip("-") or "font"
    suffix = ".otf" if blob[:4] == b"OTTO" else ".ttf"
    (FONT_DIR / f"{safe}{suffix}").write_bytes(blob)
    _refresh_font_cache()

    if is_installed_after_refresh(detected):
        return FontStatus(detected, INSTALLED, source="upload")
    return FontStatus(detected, UNAVAILABLE,
                      reason=f"Fontti '{detected}' tallennettiin, mutta "
                             "järjestelmä ei tunnista sitä asennetuksi.")


def remove_font_file(family: str) -> bool:
    """Delete what install_font_bytes wrote for *family*. True if anything went."""
    safe = re.sub(r"[^A-Za-z0-9]+", "-", family).strip("-")
    removed = False
    for suffix in (".ttf", ".otf"):
        path = FONT_DIR / f"{safe}{suffix}"
        if path.exists():
            path.unlink()
            removed = True
    if removed:
        _refresh_font_cache()
        installed_families(refresh=True)
    return removed


def ensure_font(family: str, *, allow_network: bool = True,
                timeout: float = _TIMEOUT, fetch=None) -> FontStatus:
    """Make *family* usable on this host, or explain why it cannot be."""
    family = (family or "").strip()
    if not family:
        return FontStatus("", UNAVAILABLE, reason="Pohja ei nimeä fonttia.")
    if is_installed(family):
        return FontStatus(family, PRESENT, source="system")
    if not allow_network:
        return FontStatus(family, UNAVAILABLE,
                          reason=f"Fonttia '{family}' ei ole asennettu, "
                                 "eikä verkkohaku ole käytössä.")

    url, reason = google_font_url(family, timeout=timeout, fetch=fetch)
    if url is None:
        return FontStatus(family, UNAVAILABLE, reason=reason)

    try:
        blob = (fetch or _fetch)(url, timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return FontStatus(family, UNAVAILABLE,
                          reason=f"Fontin '{family}' lataus epäonnistui "
                                 f"({exc.__class__.__name__}).")
    if not blob:
        return FontStatus(family, UNAVAILABLE,
                          reason=f"Fontin '{family}' lataus palautti tyhjän tiedoston.")
    st = install_font_bytes(blob, filename=f"{family}.ttf", family=family)
    if st.state == INSTALLED:
        return FontStatus(family, INSTALLED, source="google-fonts")
    if not blob.startswith(_SFNT_MAGIC):
        return FontStatus(family, UNAVAILABLE,
                          reason=f"Fontista '{family}' saatiin verkkomuotoinen "
                                 "tiedosto (WOFF/EOT), jota palvelin ei osaa "
                                 "käyttää.")
    return st


def is_installed_after_refresh(family: str) -> bool:
    """Re-read fontconfig, then check. Used right after installing a file."""
    return family.strip().lower() in installed_families(refresh=True)


def check_template_fonts(families, *, allow_network: bool = True,
                         fetch=None) -> list[FontStatus]:
    """Resolve every font a template names, de-duplicated, order preserved."""
    seen: set[str] = set()
    out: list[FontStatus] = []
    for family in families:
        key = (family or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(ensure_font(family, allow_network=allow_network, fetch=fetch))
    return out
