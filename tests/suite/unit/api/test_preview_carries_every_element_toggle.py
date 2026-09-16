"""Every element toggle reaches the preview, not just the ones anybody remembered.

`group_base` was added to `ElementToggles`, honoured by every renderer, and
saved correctly in the report — and unticking it changed nothing on screen,
because the PREVIEW takes a different road. `_ElementTogglesBody` is its own
model and `ChartSpec` was built from it field by field:

    elements=ElementToggles(
        title=body.elements.title,
        subtitle=body.elements.subtitle,
        ...                      # seven named fields, and the new one nowhere

So the deck honoured the switch and the editor — the only place the author can
see their own change — silently did not.

`previewFingerprint.ts` records the same lesson about the same shape of list:
"an allow-list of twenty-five named fields ... meant every new ChartSpec field
had to be remembered there or the preview silently kept showing the old image —
a bug that looks like a broken renderer, and that no reviewer of the new field
would think to look for."

So this compares the two SETS rather than checking one field. The next toggle
fails here, at the moment it is added, instead of being reported as a control
that does nothing. (Johan, 2026-09-16)
"""
from __future__ import annotations

import dataclasses

import pytest

from reportbuilder.api.routes_questions import _ElementTogglesBody
from reportbuilder.model.report import ElementToggles

pytestmark = pytest.mark.unit


def _toggle_fields() -> set[str]:
    return {f.name for f in dataclasses.fields(ElementToggles)}


def _body_fields() -> set[str]:
    return set(_ElementTogglesBody.model_fields)


def test_the_preview_body_offers_every_toggle():
    missing = _toggle_fields() - _body_fields()
    assert not missing, (
        f"{sorted(missing)} can be set on a slide but not sent to the preview, "
        f"so the editor will not show what the deck draws")


def test_the_preview_body_invents_none():
    extra = _body_fields() - _toggle_fields()
    assert not extra, f"{sorted(extra)} is sent to the preview and means nothing"


def test_the_defaults_agree():
    """A toggle defaulting to on in one and off in the other would make a fresh
    slide and its own preview disagree."""
    spec_defaults = {f.name: f.default for f in dataclasses.fields(ElementToggles)}
    body_defaults = {n: f.default for n, f in _ElementTogglesBody.model_fields.items()}
    assert spec_defaults == body_defaults


def test_the_body_round_trips_into_the_dataclass():
    """What the preview receives must build the real toggles without naming
    fields one by one — that hand-written list is what went stale."""
    body = _ElementTogglesBody(group_base=False, legend=False)
    toggles = ElementToggles(**body.model_dump())
    assert toggles.group_base is False
    assert toggles.legend is False
    assert toggles.title is True
