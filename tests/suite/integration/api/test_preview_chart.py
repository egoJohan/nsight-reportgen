"""Integration tests for POST /materials/{mid}/preview-chart (routes_questions).

Guard ORDER in the route is load-bearing (no soffice → 503 FIRST, then scatter,
then stacked). To assert the 422 GUARDS deterministically WITHOUT LibreOffice we
patch `routes_questions.shutil.which` to a truthy value so the 503 guard passes
but the render chain is never reached (the guards raise first). The 503 path
instead patches `which` to None. The 200-PNG success + cache-reuse paths need a
real render and are `@pytest.mark.export` + `require_soffice`.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


def _spec(**overrides) -> dict:
    body = {
        "question_ref": "q1",
        "chart_type": "vertical_bar",
        "statistic": "pct",
        "classifying_var": None,
        "number_format": {"mode": "auto"},
        "sort": {"basis": "data_order", "descending": True},
        "elements": {},
    }
    body.update(overrides)
    return body


# ---------------------------------------------------------------------------
# soffice-free guard assertions (patch `which` truthy so the 503 guard passes)
# ---------------------------------------------------------------------------


def test_scatter_without_scatter_xy_is_422(client_mock):
    """Scatter needs explicit X/Y variables; missing scatter_xy → 422 (RX-be.2)."""
    with patch("reportbuilder.api.routes_questions.shutil.which",
               return_value="soffice"):
        r = client_mock.post(
            "/materials/mat-scatter/preview-chart",
            json=_spec(chart_type="scatter", question_ref="q1"),
        )
    assert r.status_code == 422
    assert "scatter" in r.json()["detail"].lower()


def test_stacked_vertical_bar_without_classifying_var_is_422(client_mock):
    """A non-battery stacked chart needs a classifying variable for its segments;
    the 422 detail names the classifying variable (RX-be.3).

    q1 is a single (non-battery) question so the battery exemption does not apply.
    """
    # TODO(stacked-total-only): becomes 200 when the queued fix lands
    with patch("reportbuilder.api.routes_questions.shutil.which",
               return_value="soffice"):
        r = client_mock.post(
            "/materials/mat-stacked-v/preview-chart",
            json=_spec(chart_type="stacked_vertical_bar", question_ref="q1"),
        )
    assert r.status_code == 422
    assert "classifying variable" in r.json()["detail"].lower()


def test_stacked_horizontal_bar_without_classifying_var_is_422(client_mock):
    """Same guard for the horizontal stacked variant (RX-be.3)."""
    # TODO(stacked-total-only): becomes 200 when the queued fix lands
    with patch("reportbuilder.api.routes_questions.shutil.which",
               return_value="soffice"):
        r = client_mock.post(
            "/materials/mat-stacked-h/preview-chart",
            json=_spec(chart_type="stacked_horizontal_bar", question_ref="q1"),
        )
    assert r.status_code == 422
    assert "classifying variable" in r.json()["detail"].lower()


def test_valid_bar_returns_503_when_soffice_absent(client_mock):
    """When LibreOffice is unavailable, even a valid bar spec cannot be rendered
    → 503 (the soffice guard runs FIRST, before the scatter/stacked guards)."""
    with patch("reportbuilder.api.routes_questions.shutil.which",
               return_value=None):
        r = client_mock.post(
            "/materials/mat-503/preview-chart",
            json=_spec(chart_type="vertical_bar"),
        )
    assert r.status_code == 503


# ---------------------------------------------------------------------------
# Full render success + cache reuse (needs real LibreOffice) — export-gated
# ---------------------------------------------------------------------------


@pytest.mark.export
def test_valid_bar_returns_png(client_mock, require_soffice):
    """The happy path renders a real PNG thumbnail (magic bytes b"\\x89PNG")."""
    r = client_mock.post(
        "/materials/mat-png-ok/preview-chart",
        json=_spec(chart_type="vertical_bar", question_ref="q1"),
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:4] == b"\x89PNG"


@pytest.mark.export
def test_identical_spec_served_from_cache(client_mock, require_soffice):
    """Two identical preview requests render the chain ONCE; the second is served
    from the deterministic per-(process, material, spec) cache — asserted by
    patching build_pptx as a spy over the real render and counting one call."""
    from reportbuilder.api import routes_questions as rq

    calls = {"n": 0}
    real_build = rq.build_pptx

    def spy_build(*a, **k):
        calls["n"] += 1
        return real_build(*a, **k)

    spec = _spec(chart_type="vertical_bar", question_ref="q1")
    mat = "mat-cache-reuse"  # unique id → no cross-test cache pollution
    with patch.object(rq, "build_pptx", side_effect=spy_build):
        r1 = client_mock.post(f"/materials/{mat}/preview-chart", json=spec)
        r2 = client_mock.post(f"/materials/{mat}/preview-chart", json=spec)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.content == r2.content
    assert r1.content[:4] == b"\x89PNG"
    # The expensive build ran exactly once; the second call hit the cache.
    assert calls["n"] == 1, f"expected 1 underlying render, got {calls['n']}"
