"""A font the template names must not vanish from the template's own row.

The upload check reads every family the FILE names — theme fonts plus whatever
the slide master sets — and records what it could not resolve. The listing
re-checks against the host as it is now, so installing a font clears the row
instead of leaving it stale.

The bug: the re-check was driven only by the theme's heading/body pair, and it
built its output from that list. Anything recorded from the master — Barlow
Condensed, in the case that surfaced this — was simply absent from the result.
So the upload warned about a font the template row then denied naming, and an
admin had nothing to act on.
"""
from __future__ import annotations

import pytest

from reportbuilder.api.routes_templates import _live_font_status

pytestmark = pytest.mark.unit


def _stored(family: str, ok: bool = False) -> dict:
    return {"family": family, "ok": ok,
            "reason": "not an open-licence font, cannot be installed"}


def test_a_recorded_font_survives_the_recheck(monkeypatch):
    """Even though the caller only knows the theme's two families."""
    from reportbuilder.render import fonts as font_mod

    class _St:
        def __init__(self, family, ok):
            self.family, self.ok = family, ok

        def as_dict(self):
            return {"family": self.family, "ok": self.ok}

    monkeypatch.setattr(font_mod, "check_template_fonts",
                        lambda families, allow_network=True: [
                            _St(f, False) for f in families])

    out = _live_font_status([_stored("Barlow Condensed")], ["Arial"])
    families = [f["family"] for f in out]
    assert "Barlow Condensed" in families, (
        "a font recorded at upload disappeared from the listing")
    assert "Arial" in families


def test_the_stored_reason_wins_for_a_font_still_unresolved(monkeypatch):
    """The stored row explains the licence; a network-free re-check can only
    say the font is absent."""
    from reportbuilder.render import fonts as font_mod

    class _St:
        def __init__(self, family, ok):
            self.family, self.ok = family, ok

        def as_dict(self):
            return {"family": self.family, "ok": self.ok, "reason": "not installed"}

    monkeypatch.setattr(font_mod, "check_template_fonts",
                        lambda families, allow_network=True: [
                            _St(f, False) for f in families])

    [row] = [f for f in _live_font_status([_stored("Barlow Condensed")], [])
             if f["family"] == "Barlow Condensed"]
    assert "licence" in row["reason"]


def test_a_font_installed_since_upload_clears(monkeypatch):
    """The whole reason the listing re-checks at all."""
    from reportbuilder.render import fonts as font_mod

    class _St:
        def __init__(self, family, ok):
            self.family, self.ok = family, ok

        def as_dict(self):
            return {"family": self.family, "ok": self.ok}

    monkeypatch.setattr(font_mod, "check_template_fonts",
                        lambda families, allow_network=True: [
                            _St(f, True) for f in families])

    out = _live_font_status([_stored("Barlow Condensed")], [])
    assert [f["ok"] for f in out] == [True]


def test_no_duplicate_rows_when_the_theme_font_was_also_recorded(monkeypatch):
    from reportbuilder.render import fonts as font_mod

    class _St:
        def __init__(self, family, ok):
            self.family, self.ok = family, ok

        def as_dict(self):
            return {"family": self.family, "ok": self.ok}

    monkeypatch.setattr(font_mod, "check_template_fonts",
                        lambda families, allow_network=True: [
                            _St(f, False) for f in families])

    out = _live_font_status([_stored("Arial")], ["Arial"])
    assert [f["family"] for f in out] == ["Arial"]
