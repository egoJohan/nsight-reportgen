"""A template names fonts it does not carry; these cover what we do about it.

The network is never touched: every test injects a fetcher. A test that
depended on Google Fonts being reachable would fail on a plane and pass for
the wrong reason on a machine that happened to have the font.
"""
import urllib.error

import pytest

from reportbuilder.render import fonts


OPEN_CSS = b"""@font-face {
  font-family: 'Questrial';
  font-style: normal;
  src: url(https://fonts.gstatic.com/s/questrial/v19/QdVUSTchPBm7nuUeVf70viFg.ttf) format('truetype');
}"""

# The library listing, XSSI-prefixed exactly as Google serves it. Century Gothic
# and Calibri are absent: Google SERVES them, but they are not open-licence and
# so are not ours to install.
LIBRARY = b""")]}'
{"familyMetadataList": [
  {"family": "Questrial", "isOpenSource": true},
  {"family": "Roboto", "isOpenSource": true},
  {"family": "Brand Sans", "isOpenSource": false}
]}"""

# A real TrueType file starts with this; a WOFF or EOT does not.
TTF = b"\x00\x01\x00\x00" + b"rest-of-a-font"


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    """Install into a temp dir and never shell out to fc-cache."""
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path / "fonts")
    monkeypatch.setattr(fonts, "_refresh_font_cache", lambda: None)
    monkeypatch.setattr(fonts, "_installed_cache", None, raising=False)
    monkeypatch.setattr(fonts, "_library_cache", None, raising=False)


def _fetcher(pages: dict, calls: list | None = None):
    def fetch(url, timeout):
        if calls is not None:
            calls.append(url)
        for needle, payload in pages.items():
            if needle in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise urllib.error.HTTPError(url, 400, "Bad Request", {}, None)
    return fetch


# --- already on the host ----------------------------------------------------

def test_installed_font_is_used_without_touching_the_network(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: {"liberation sans"})
    calls = []
    st = fonts.ensure_font("Liberation Sans", fetch=_fetcher({"metadata/fonts": LIBRARY}, calls))

    assert st.state == fonts.PRESENT
    assert st.ok and st.source == "system"
    assert calls == []          # nothing fetched for a font we already have


def test_installed_check_is_case_insensitive(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: {"noto sans"})
    assert fonts.is_installed("NOTO SANS")


# --- fetched from the cloud -------------------------------------------------

def test_open_licence_font_is_downloaded_and_installed(monkeypatch):
    state = {"installed": False}
    monkeypatch.setattr(fonts, "installed_families",
                        lambda **_: {"questrial"} if state["installed"] else set())

    def fake_refresh():
        state["installed"] = True      # fc-cache picks the new file up
    monkeypatch.setattr(fonts, "_refresh_font_cache", fake_refresh)

    fetch = _fetcher({"metadata/fonts": LIBRARY,
                      "css?family=Questrial": OPEN_CSS, "/s/questrial": TTF})
    st = fonts.ensure_font("Questrial", fetch=fetch)

    assert st.state == fonts.INSTALLED
    assert st.source == "google-fonts"
    assert (fonts.FONT_DIR / "Questrial.ttf").read_bytes() == TTF


def test_download_that_fontconfig_never_sees_is_reported_unavailable(monkeypatch):
    """A file on disk is not the same as an installed font.

    If fontconfig does not report it, LibreOffice will substitute at render
    time — the very silence this module exists to prevent — so claiming success
    here would be worse than useless.
    """
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    fetch = _fetcher({"metadata/fonts": LIBRARY,
                      "css?family=Questrial": OPEN_CSS, "/s/questrial": TTF})

    st = fonts.ensure_font("Questrial", fetch=fetch)

    assert st.state == fonts.UNAVAILABLE
    assert "ei tunnista sitä asennetuksi" in st.reason


# --- the licence line -------------------------------------------------------

def test_commercially_licensed_font_is_never_downloaded(monkeypatch):
    """Google serves Century Gothic; that licence is Google's, not ours."""
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    calls = []
    fetch = _fetcher({"metadata/fonts": LIBRARY}, calls)

    st = fonts.ensure_font("Century Gothic", fetch=fetch)

    assert st.state == fonts.UNAVAILABLE
    assert not st.ok
    assert "ei ole avoimen lisenssin fontti" in st.reason
    # Only the licence listing was read — no CSS, no font file.
    assert len(calls) == 1 and "metadata/fonts" in calls[0]


def test_font_in_the_library_but_not_open_source_is_refused(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    st = fonts.ensure_font("Brand Sans", fetch=_fetcher({"metadata/fonts": LIBRARY}))

    assert st.state == fonts.UNAVAILABLE
    assert "ei avoimella" in st.reason


def test_unreadable_licence_listing_refuses_rather_than_assumes(monkeypatch):
    """No listing means no licence evidence, and no evidence means no install."""
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    calls = []
    fetch = _fetcher({"metadata/fonts": urllib.error.URLError("offline")}, calls)

    st = fonts.ensure_font("Questrial", fetch=fetch)

    assert st.state == fonts.UNAVAILABLE
    assert "lisenssitietoja ei saatu" in st.reason
    assert all("gstatic" not in c for c in calls)


def test_web_font_format_is_rejected_not_installed(monkeypatch):
    """WOFF/EOT is a font the browser can use and fontconfig cannot.

    Installing one would leave every render silently substituting while the UI
    reported the font as available.
    """
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    fetch = _fetcher({"metadata/fonts": LIBRARY,
                      "css?family=Questrial": OPEN_CSS,
                      "/s/questrial": b"wOFF" + b"not-an-sfnt"})

    st = fonts.ensure_font("Questrial", fetch=fetch)

    assert st.state == fonts.UNAVAILABLE
    assert "WOFF/EOT" in st.reason
    assert not (fonts.FONT_DIR / "Questrial.ttf").exists()


def test_unknown_family_is_reported_not_guessed(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    st = fonts.ensure_font("Totally Made Up Sans",
                           fetch=_fetcher({"metadata/fonts": LIBRARY}))

    assert st.state == fonts.UNAVAILABLE
    assert "ei ole avoimen lisenssin fontti" in st.reason


# --- failure modes that must not break a render -----------------------------

def test_network_failure_is_reported_rather_than_raised(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    fetch = _fetcher({"metadata/fonts": LIBRARY,
                      "css?family": urllib.error.URLError("offline")})

    st = fonts.ensure_font("Questrial", fetch=fetch)

    assert st.state == fonts.UNAVAILABLE
    assert "ei saatu yhteyttä" in st.reason


def test_network_can_be_switched_off_entirely(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    calls = []
    st = fonts.ensure_font("Questrial", allow_network=False,
                           fetch=_fetcher({"metadata/fonts": LIBRARY}, calls))

    assert st.state == fonts.UNAVAILABLE
    assert calls == []
    assert "verkkohaku ole käytössä" in st.reason


def test_blank_family_is_not_an_error_worth_fetching(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: set())
    st = fonts.ensure_font("   ", fetch=_fetcher({"metadata/fonts": LIBRARY}))
    assert st.state == fonts.UNAVAILABLE
    assert "ei nimeä fonttia" in st.reason


# --- template-level check ---------------------------------------------------

def test_check_template_fonts_dedupes_and_keeps_order(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: {"verdana"})
    out = fonts.check_template_fonts(["Verdana", "verdana ", "", "Verdana"],
                                     fetch=_fetcher({"metadata/fonts": LIBRARY}))
    assert [s.family for s in out] == ["Verdana"]
    assert out[0].ok


def test_check_template_fonts_reports_each_font_separately(monkeypatch):
    """A heading font we have and a body font we do not must not blur together."""
    monkeypatch.setattr(fonts, "installed_families", lambda **_: {"verdana"})
    fetch = _fetcher({"metadata/fonts": LIBRARY})

    out = fonts.check_template_fonts(["Century Gothic", "Verdana"], fetch=fetch)

    assert [(s.family, s.ok) for s in out] == [("Century Gothic", False), ("Verdana", True)]


def test_status_serialises_for_the_api(monkeypatch):
    monkeypatch.setattr(fonts, "installed_families", lambda **_: {"verdana"})
    d = fonts.ensure_font("Verdana", fetch=_fetcher({"metadata/fonts": LIBRARY})).as_dict()
    assert d == {"family": "Verdana", "state": "present", "source": "system",
                 "reason": "", "ok": True}
