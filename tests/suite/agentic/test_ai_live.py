"""Live egoHive smoke tests (``@pytest.mark.live``).

These make REAL calls to a local egoHive instance using the actual
``egohive_chat`` (never monkeypatched). Config is read from the environment or
``work/egohive_creds.json``. When egoHive is unconfigured/unreachable the real
call raises ``EgoHiveError`` and the test self-SKIPS — so the suite stays green
without a backend.

Note: egohive_client wraps most transport errors as EgoHiveError, but a
mid-stream ``ConnectionResetError`` (an ``OSError``) can escape unwrapped, so we
skip on ``(EgoHiveError, OSError)`` to stay robust in a network-restricted env.
"""
from __future__ import annotations

import pytest

from nsight.agent.egohive_client import EgoHiveError, egohive_chat
from reportbuilder.ai.text import (
    generate_conclusion_bullets,
    generate_slide_title,
    shorten_labels,
)
from reportbuilder.ai.reference import ReferenceLabels


pytestmark = pytest.mark.live

# egoHive-unreachable signals: the wrapped error plus any raw transport OSError
# that escapes the client (e.g. ConnectionResetError in a sandboxed network).
_UNREACHABLE = (EgoHiveError, OSError)


def test_live_slide_title_smoke():
    try:
        title = generate_slide_title(
            "Kuinka tyytyväinen olet palveluun?",
            [("Erittäin tyytyväinen", 62.0), ("Melko tyytyväinen", 28.0)],
            chat=egohive_chat,
        )
    except _UNREACHABLE as exc:
        pytest.skip(f"egoHive unreachable: {exc}")
    assert isinstance(title, str) and title.strip()


def test_live_conclusion_bullets_smoke():
    try:
        bullets = generate_conclusion_bullets(
            "Asiakastutkimus",
            [("Tyytyväisyys palveluun", [("Erittäin tyytyväinen", 62.0), ("Tyytymätön", 8.0)])],
            chat=egohive_chat,
        )
    except _UNREACHABLE as exc:
        pytest.skip(f"egoHive unreachable: {exc}")
    assert isinstance(bullets, list)
    assert all(isinstance(b, str) and b.strip() for b in bullets)


def test_live_shorten_labels_smoke():
    reference = ReferenceLabels(labels=[], titles=[])
    try:
        out = shorten_labels(
            ["Erittäin tai melko tyytyväiset asiakkaat"],
            reference=reference,
            chat=egohive_chat,
        )
    except _UNREACHABLE as exc:
        pytest.skip(f"egoHive unreachable: {exc}")
    # Whatever comes back must be well-formed (full, short) pairs.
    assert isinstance(out, list)
    for full, short in out:
        assert isinstance(full, str) and isinstance(short, str)


def test_live_route_slide_title_smoke(client_mock, monkeypatch):
    """End-to-end through the route with the REAL egoHive seam (no patching)."""
    import reportbuilder.api.routes_ai as R

    # Ensure any earlier monkeypatch in the process didn't leave a fake in place.
    monkeypatch.setattr(R, "egohive_chat", egohive_chat)
    resp = client_mock.post("/materials/live/ai/slide-title", json={"question_ref": "q1"})
    if resp.status_code == 503:
        pytest.skip("egoHive unreachable (route returned 503)")
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"].strip()
