"""preview-chart reuses a generated image instead of re-rendering.

The render chain (build_pptx → pptx_to_pdf → rasterize) is expensive
(LibreOffice). A given (process, material, spec) must be rendered ONCE and
reused; only a changed spec re-renders.
"""
from __future__ import annotations

from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from reportbuilder.api.app import create_app
from reportbuilder.testing.fixtures import synthetic_sav_bytes

_SPEC = {
    "question_ref": "q1",
    "chart_type": "vertical_bar",
    "statistic": "pct",
    "classifying_var": None,
    "number_format": {"mode": "auto"},
    "sort": {"basis": "pct", "descending": True},
    "template_slot": "s1",
    "elements": {},
}


def _client():
    mock = Mock()
    mock.get_material.return_value = synthetic_sav_bytes()
    return TestClient(create_app(client=mock))


def test_identical_spec_renders_once_then_serves_from_cache(tmp_path):
    """Two identical preview requests → the render chain runs ONCE; the second is
    served from the cached PNG. A different spec renders again."""
    png = tmp_path / "p.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)

    calls = {"build": 0}

    def fake_build(*a, **k):
        calls["build"] += 1

    with patch("reportbuilder.api.routes_questions.shutil.which", return_value="soffice"), \
         patch("reportbuilder.api.routes_questions.build_pptx", side_effect=fake_build), \
         patch("reportbuilder.api.routes_questions.pptx_to_pdf", return_value=str(tmp_path / "d.pdf")), \
         patch("reportbuilder.api.routes_questions.rasterize_pages", return_value=[str(png)]):
        client = _client()
        mat = "mat-cache-unique"  # unique id so no cross-test cache pollution

        r1 = client.post(f"/materials/{mat}/preview-chart", json=_SPEC)
        r2 = client.post(f"/materials/{mat}/preview-chart", json=_SPEC)
        assert r1.status_code == 200 and r2.status_code == 200
        assert r1.content == r2.content
        assert calls["build"] == 1, f"expected 1 render for identical spec, got {calls['build']}"

        # A different spec must render again.
        other = {**_SPEC, "chart_type": "horizontal_bar"}
        r3 = client.post(f"/materials/{mat}/preview-chart", json=other)
        assert r3.status_code == 200
        assert calls["build"] == 2, f"changed spec should re-render, got {calls['build']}"
