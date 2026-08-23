"""Make a template's fonts real, or say plainly that we cannot.

A PowerPoint template only NAMES its fonts; it does not carry them. When the
render host lacks one, nothing fails — fontconfig quietly substitutes, LibreOffice
draws the deck in Noto Sans, and the output looks subtly unlike the customer's
brand with no indication why. That silence is the problem this module removes.

What a missing font actually costs, which is narrower than it first appears:

  * The .pptx is NOT damaged. Slide text lives in placeholders and textboxes
    that NAME the font, so a deck built here still says "Century Gothic" and
    renders correctly on any machine that has it. Verified by reading the
    theme of a deck produced on a host without the font.
  * The PDF and the on-screen previews ARE affected. Both are rasterised here,
    so they show whatever this host could find.
  * Charts are not affected at all any more. Chart text is drawn by matplotlib
    in the font chosen in Settings — deliberately nSight's own choice, not the
    template's, because a brand display face wastes space on category labels.

So the warning is about fidelity of what we RENDER, not about the file the
analyst sends on. Worth saying accurately: overstating it teaches people to
ignore it.

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

import contextlib
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

# Where fontconfig substitution rules are written. An admin choosing a stand-in
# for a font we may not install is a render-side alias ONLY: the .pptx keeps
# naming the real font, so a client who has it still sees their own brand, while
# our PDF and previews stop falling back to whatever fontconfig picked.
SUBSTITUTION_FILE = pathlib.Path(
    os.environ.get("NSIGHT_FONTCONFIG_FILE",
                   "~/.config/fontconfig/conf.d/99-nsight-substitutions.conf")
).expanduser()

PRESENT = "present"           # the host already had it
INSTALLED = "installed"       # we fetched it and installed it just now
SUBSTITUTED = "substituted"   # an admin chose a stand-in for it
UNAVAILABLE = "unavailable"   # we cannot supply it — say so


@dataclass(frozen=True)
class FontStatus:
    """What happened when we tried to make *family* usable."""

    family: str
    state: str
    source: str = ""     # "system" | "google-fonts" | "upload"
    reason: str = ""     # populated only when UNAVAILABLE

    #: The family actually drawn with, when it differs from the one asked for.
    substitute: str = ""

    @property
    def ok(self) -> bool:
        """A deliberate substitution counts as resolved.

        The point of the warning was never "this is not the exact font" — it
        was "something was swapped in and nobody told you". Once an admin has
        chosen the stand-in, they have been told.
        """
        return self.state in (PRESENT, INSTALLED, SUBSTITUTED)

    def as_dict(self) -> dict:
        return {"family": self.family, "state": self.state,
                "source": self.source, "reason": self.reason,
                "substitute": self.substitute, "ok": self.ok}


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
        return None, ("Could not fetch the font library's licence data, so "
                      f"'{family}' will not be installed.")
    if key not in library:
        return None, (f"'{family}' is not an open-licence font (a Monotype or "
                      "Microsoft font, say), so it cannot be installed "
                      "automatically. The PowerPoint file still refers to the "
                      "right font, and will use it on any machine that has it — "
                      "only the preview and the PDF show a stand-in. Install "
                      "the font in Settings if you want those right too.")
    if not library[key]:
        return None, (f"'{family}' is on Google Fonts, but not under an open "
                      "licence, so it cannot be installed on the server.")

    quoted = family.strip().replace(" ", "+")
    try:
        body = fetch(_CSS_URL.format(family=quoted), timeout).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 400:
            return None, f"Google Fonts ei tunne fonttia '{family}'."
        return None, f"Google Fonts vastasi virheellä {exc.code}."
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return None, f"Could not reach Google Fonts ({exc.__class__.__name__})."

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


# --- substitutions ----------------------------------------------------------

_SUB_HEADER = """<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<!-- Written by nSight. Edited through Settings, not by hand. -->
<fontconfig>
"""
_SUB_RULE = """  <match target="pattern">
    <test name="family"><string>{missing}</string></test>
    <edit name="family" mode="assign" binding="strong"><string>{use}</string></edit>
  </match>
"""

_substitutions: dict[str, str] = {}


def substitutions() -> dict[str, str]:
    """The active missing-font -> stand-in map."""
    return dict(_substitutions)


def rendering_fingerprint() -> str:
    """A short hash of every host setting that changes how a slide is drawn.

    Belongs in every cache key for a rendered image. A cached preview is a
    picture of a chart in a template AS THIS HOST DRAWS IT, and a stand-in font
    changes that without changing the chart or the template — so an admin who
    picked a new stand-in kept being served the picture drawn with the old one.
    """
    import hashlib
    import json

    from reportbuilder.render import house_style as H

    try:
        chart_font = H.current_chart_font()
    except Exception:  # noqa: BLE001 — a fingerprint must never break a render
        chart_font = ""
    raw = json.dumps({"subs": substitutions(), "chart_font": chart_font},
                     sort_keys=True)
    return hashlib.md5(raw.encode()).hexdigest()[:8]


def apply_substitutions(mapping: dict[str, str]) -> dict[str, str]:
    """Install fontconfig rules so *mapping* takes effect for rendering.

    Deliberately NOT applied by rewriting the deck: the .pptx keeps naming the
    real font so it still renders correctly wherever that font exists. Only
    what we rasterise here — the PDF and the previews — changes.
    """
    global _substitutions
    from xml.sax.saxutils import escape

    clean = {k.strip(): v.strip() for k, v in (mapping or {}).items()
             if k and k.strip() and v and v.strip()}
    SUBSTITUTION_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not clean:
        # No rules left: remove the file rather than leave an empty one, so the
        # host goes back to exactly its pre-nSight behaviour.
        with contextlib.suppress(OSError):
            SUBSTITUTION_FILE.unlink()
    else:
        body = "".join(_SUB_RULE.format(missing=escape(k), use=escape(v))
                       for k, v in sorted(clean.items()))
        SUBSTITUTION_FILE.write_text(_SUB_HEADER + body + "</fontconfig>\n",
                                     encoding="utf-8")
    # No fc-cache here, deliberately. A conf.d rule is read when a process
    # starts, so LibreOffice picks it up on the next render with no cache
    # rebuild — and `fc-cache -f` costs ~2s, which was the whole delay between
    # choosing a stand-in and seeing it. Verified both ways: writing the file
    # changes fc-match immediately, and deleting it reverts immediately.
    #
    # installed_families is untouched for the same reason: an alias redirects a
    # lookup, it does not add a family to fc-list.
    _substitutions = clean
    return clean


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
                          reason="The file is empty.")
    if not blob.startswith(_SFNT_MAGIC):
        return FontStatus(
            family or filename, UNAVAILABLE,
            reason="The file is not a .ttf or .otf font. Web fonts (WOFF, "
                   "WOFF2, EOT) cannot be installed on the server.")

    detected = family or family_of(blob)
    if not detected:
        return FontStatus(filename, UNAVAILABLE,
                          reason="Could not read the font name out of the file.")

    FONT_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9]+", "-", detected).strip("-") or "font"
    suffix = ".otf" if blob[:4] == b"OTTO" else ".ttf"
    (FONT_DIR / f"{safe}{suffix}").write_bytes(blob)
    _refresh_font_cache()

    if is_installed_after_refresh(detected):
        return FontStatus(detected, INSTALLED, source="upload")
    return FontStatus(detected, UNAVAILABLE,
                      reason=f"'{detected}' was saved, but the system does "
                             "not recognise it as installed.")


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
        return FontStatus("", UNAVAILABLE, reason="The template names no font.")
    if is_installed(family):
        return FontStatus(family, PRESENT, source="system")
    stand_in = _substitutions.get(family)
    if stand_in:
        return FontStatus(
            family, SUBSTITUTED, source="substitution", substitute=stand_in,
            reason=f"'{family}' is replaced by '{stand_in}' in previews and "
                   "in the PDF. The PowerPoint file still refers to "
                   f"'{family}'.")
    if not allow_network:
        return FontStatus(family, UNAVAILABLE,
                          reason=f"'{family}' is not installed, and network "
                                 "lookup is switched off.")

    url, reason = google_font_url(family, timeout=timeout, fetch=fetch)
    if url is None:
        return FontStatus(family, UNAVAILABLE, reason=reason)

    try:
        blob = (fetch or _fetch)(url, timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return FontStatus(family, UNAVAILABLE,
                          reason=f"Downloading '{family}' failed "
                                 f"({exc.__class__.__name__}).")
    if not blob:
        return FontStatus(family, UNAVAILABLE,
                          reason=f"Downloading '{family}' returned an empty file.")
    st = install_font_bytes(blob, filename=f"{family}.ttf", family=family)
    if st.state == INSTALLED:
        return FontStatus(family, INSTALLED, source="google-fonts")
    if not blob.startswith(_SFNT_MAGIC):
        return FontStatus(family, UNAVAILABLE,
                          reason=f"'{family}' came back as a web-format file "
                                 "(WOFF/EOT), which the server cannot use.")
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

# Typefaces that are never a template's design choice: theme references
# ("+mj-lt"), and the CJK/symbol families PowerPoint writes alongside every
# latin run whether or not the deck contains a word of Japanese.
_NOT_A_DESIGN_CHOICE = {
    "ＭＳ ｐゴシック", "ＭＳ pゴシック", "맑은 고딕", "wingdings", "symbol",
}


def families_in_template(pptx_path: str) -> list[str]:
    """Every typeface the template actually names, most-used first.

    The theme's major/minor pair is NOT the whole story and on real decks is
    rarely even the interesting part: Egoiq_x_Rahoo declares Arial for both,
    while its master sets the title in Bebas Neue and the body in Barlow
    Condensed Medium. Checking only the theme meant nSight never learned it
    needed either, never fetched them though both are open-licence Google
    families, and rendered the customer's headline in a substitute — in the
    deck AND in the preview, differently.

    Reads the masters, layouts, theme and any slides, because a font can be
    named in any of them.
    """
    import collections
    import re
    import zipfile

    counts: collections.Counter = collections.Counter()
    try:
        with zipfile.ZipFile(pptx_path) as z:
            for name in z.namelist():
                if not name.endswith(".xml"):
                    continue
                if not any(part in name for part in
                           ("slideMaster", "slideLayout", "theme", "slides/")):
                    continue
                # <a:latin> only. A theme also carries a <a:font script="..">
                # fallback table — Mongolian Baiti, DokChampa, thirty more —
                # that PowerPoint writes into every file and nobody chose;
                # fetching those would be dozens of pointless downloads.
                for raw in re.findall(rb'<a:latin[^>]*typeface="([^"]+)"', z.read(name)):
                    family = raw.decode("utf-8", "replace").strip()
                    if not family or family.startswith("+"):
                        continue
                    if family.lower() in _NOT_A_DESIGN_CHOICE:
                        continue
                    counts[family] += 1
    except (OSError, zipfile.BadZipFile, KeyError):
        return []
    return [f for f, _n in counts.most_common()]
