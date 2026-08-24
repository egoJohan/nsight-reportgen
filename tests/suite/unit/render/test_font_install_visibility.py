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
    for candidate in pathlib.Path("/usr/share/fonts").rglob("*.ttf"):
        blob = candidate.read_bytes()
        family = fonts.family_of(blob)
        if not family:
            continue
        try:                                  # loadable by matplotlib?
            font_manager.FontProperties(family=family)
            font_manager.fontManager.addfont(str(candidate))
        except Exception:                     # noqa: BLE001 — colour emoji, etc.
            continue
        return blob, family, candidate.name
    pytest.skip("no usable font on this host")


def test_the_image_renderer_can_use_it_without_a_restart(monkeypatch, tmp_path):
    blob, family, filename = _a_real_font()
    fm = font_manager.fontManager
    original = list(fm.ttflist)
    try:
        # The state a process is in when an admin installs a font it started
        # without: matplotlib has never heard of this family.
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
    finally:
        fm.ttflist = original


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

    # It still wrote the file and still answered — the refusal is swallowed.
    assert list(tmp_path.iterdir()), "the font was not written"
    assert status.state in (fonts.INSTALLED, fonts.UNAVAILABLE)
