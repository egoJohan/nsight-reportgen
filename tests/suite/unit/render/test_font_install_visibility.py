"""A font installed today has to work today.

Installing one writes the file and refreshes fontconfig, which is enough for
LibreOffice: it starts a fresh process per render and re-reads fontconfig every
time. matplotlib — the IMAGE renderer, which is what every preview goes through
— does not. It builds its font list once per process and keeps it.

So a font uploaded through Settings was verified through fontconfig, reported
INSTALLED, and then went on being substituted in every preview until somebody
restarted the server, with the settings page saying, correctly and uselessly,
that it was there.
"""
from __future__ import annotations

import pathlib
import tempfile

import pytest
from matplotlib import font_manager

from reportbuilder.render import fonts


def _a_real_font() -> tuple[bytes, str, str]:
    """A font on this host that matplotlib can actually load.

    Probed with FT2Font, NOT with `addfont`: addfont mutates matplotlib's
    process-wide `ttflist`, and this whole suite runs in one process alongside
    ~650 render tests. The probe used to leave every candidate it tried
    permanently registered.
    """
    from matplotlib import ft2font

    for candidate in pathlib.Path("/usr/share/fonts").rglob("*.ttf"):
        blob = candidate.read_bytes()
        family = fonts.family_of(blob)
        if not family:
            continue
        try:
            ft2font.FT2Font(str(candidate))
        except Exception:                     # noqa: BLE001 — colour emoji, etc.
            continue
        return blob, family, candidate.name
    pytest.skip("no usable font on this host")


@pytest.fixture(autouse=True)
def _restore_matplotlib_font_list():
    """Installing a font registers it for the life of the PROCESS. Put the list
    back, or these tests leave their font behind for everything after them."""
    fm = font_manager.fontManager
    original = list(fm.ttflist)
    yield
    fm.ttflist = original


def test_the_image_renderer_can_use_it_without_a_restart(monkeypatch, tmp_path):
    blob, family, filename = _a_real_font()
    fm = font_manager.fontManager
    # The state a process is in when an admin installs a font it started
    # without: matplotlib has never heard of this family. (The autouse fixture
    # puts the list back afterwards.)
    fm.ttflist = [f for f in fm.ttflist if f.name != family]
    with pytest.raises(ValueError):
        font_manager.findfont(font_manager.FontProperties(family=family),
                              fallback_to_default=False)

    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)
    status = fonts.install_font_bytes(blob, filename=filename, family=family)
    assert status.state == fonts.INSTALLED, status.reason

    chosen = pathlib.Path(font_manager.findfont(
        font_manager.FontProperties(family=family), fallback_to_default=False))
    assert str(chosen).startswith(str(tmp_path)), (
        "a preview would still be drawn in a substitute")


def test_a_font_matplotlib_cannot_load_does_not_break_the_install(monkeypatch,
                                                                  tmp_path):
    """Colour-emoji fonts are a real example: fontconfig accepts them and
    matplotlib refuses them. A 500 from the settings page over that would be
    worse than the substitution it is trying to prevent."""
    # Pick the font FIRST: the helper probes with addfont, and patching that
    # before choosing one made every candidate look unusable and skipped the
    # test — which read as "no fonts on this host" and tested nothing.
    blob, family, filename = _a_real_font()

    def explode(*_a, **_k):
        raise RuntimeError("Can not load face (unknown file format)")

    monkeypatch.setattr(font_manager.fontManager, "addfont", explode)
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)

    status = fonts.install_font_bytes(blob, filename=filename, family=family)

    # It still wrote the file, and still reports success — fontconfig sees the
    # font whatever matplotlib thinks of it, and fontconfig is what LibreOffice
    # renders through. (`in (INSTALLED, UNAVAILABLE)` was the earlier
    # assertion, which is every state reachable past the write and so could
    # not fail.)
    assert list(tmp_path.iterdir()), "the font was not written"
    assert status.state == fonts.INSTALLED, status.reason


def test_installing_a_font_invalidates_every_cached_picture(monkeypatch, tmp_path):
    """Otherwise the caches keep handing back the substituted face.

    `rendering_fingerprint` is in the key of both the preview PNG cache and the
    stored deck. It hashed the stand-in rules and the chosen chart font but not
    WHICH FONTS EXIST — so the sequence that matters went wrong: an admin names
    a chart font the host does not have (everything re-renders in the fallback,
    correctly), then uploads the .ttf. New renders were right; every cached one
    was still considered current. Previews recovered after the 24-hour sweep,
    decks never did.
    """
    blob, family, filename = _a_real_font()
    monkeypatch.setattr(fonts, "FONT_DIR", tmp_path)

    # The host as it is before the upload: this family is not installed.
    monkeypatch.setattr(fonts, "_installed_cache",
                        {f for f in fonts.installed_families() if f != family.lower()})
    before = fonts.rendering_fingerprint()

    fonts.install_font_bytes(blob, filename=filename, family=family)

    assert fonts.rendering_fingerprint() != before, (
        "every cached preview and stored deck still counts as current, "
        "drawn in the fallback face")
