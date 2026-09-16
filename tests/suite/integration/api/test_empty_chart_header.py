"""A preview of a slide with nothing to chart says so in a header.

The placeholder used to print "No data to show" across the chart area, so the
author found out by looking at the picture — and so did the client, in English,
on a slide that went out with the deck. The slide is blank now, which leaves the
editor as the only place that can raise it, and the editor only knows what the
response tells it.

`X-Chart-Empty: 1`, alongside `X-Preview-Path`, and persisted beside the cached
PNG for the same reason that one is: the cache hit returns before any rendering
and cannot work it out for itself. (Johan, 2026-09-16)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration

_RQ = "reportbuilder.api.routes_questions"


def _spec(**overrides) -> dict:
    body = {
        "question_ref": "q1",
        "chart_type": "vertical_bar",
        "statistic": "pct",
        "classifying_var": None,
        "number_format": {"mode": "auto"},
        "sort": {"basis": "data_order", "descending": True},
        "template_slot": "s1",
        "elements": {},
    }
    body.update(overrides)
    return body


def _stub_png(tmp_path) -> str:
    png = tmp_path / "page-1.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
    return str(png)


def _build_reporting(empty: bool):
    """A stand-in for the deck builder that reports the chart as blank or not.

    The render chain is stubbed here as it is in its neighbour
    test_preview_path_header — what is under test is the ROUTE turning the
    builder's report into a header, not the emptiness rule itself, which
    test_empty_chart_is_reported_to_the_author covers against real data.
    """
    def build(*a, empty_out=None, **k):
        if empty and empty_out is not None:
            empty_out.append("q1")
    return build


def test_a_blank_chart_says_so(client_mock, tmp_path):
    with patch(f"{_RQ}.shutil.which", return_value="soffice"), \
         patch(f"{_RQ}.build_pptx", side_effect=_build_reporting(True)), \
         patch(f"{_RQ}.pptx_to_pdf", return_value=str(tmp_path / "d.pdf")), \
         patch(f"{_RQ}.rasterize_pages", return_value=[_stub_png(tmp_path)]):
        r = client_mock.post(f"/materials/{client_mock.material_id}/preview-chart",
                             json=_spec())

    assert r.status_code == 200, r.text
    assert r.headers.get("X-Chart-Empty") == "1"


def test_an_ordinary_chart_says_nothing(client_mock, tmp_path):
    """Absence is the signal for "this one is fine", so it has to mean that and
    nothing else — a header on every preview would be no header."""
    with patch(f"{_RQ}.shutil.which", return_value="soffice"), \
         patch(f"{_RQ}.build_pptx", side_effect=_build_reporting(False)), \
         patch(f"{_RQ}.pptx_to_pdf", return_value=str(tmp_path / "d.pdf")), \
         patch(f"{_RQ}.rasterize_pages", return_value=[_stub_png(tmp_path)]):
        r = client_mock.post(f"/materials/{client_mock.material_id}/preview-chart",
                             json=_spec(question_ref="q1", template_slot="s2"))

    assert r.status_code == 200, r.text
    assert "X-Chart-Empty" not in r.headers


def test_the_cached_preview_says_it_too(client_mock, tmp_path):
    """The second request never builds, so it can only say this if it was told
    and wrote it down — exactly as `X-Preview-Path` is."""
    builds = {"n": 0}
    report_blank = _build_reporting(True)

    def counting(*a, **k):
        builds["n"] += 1
        report_blank(*a, **k)

    spec = _spec(template_slot="s3")
    mat = client_mock.material_id
    with patch(f"{_RQ}.shutil.which", return_value="soffice"), \
         patch(f"{_RQ}.build_pptx", side_effect=counting), \
         patch(f"{_RQ}.pptx_to_pdf", return_value=str(tmp_path / "d.pdf")), \
         patch(f"{_RQ}.rasterize_pages", return_value=[_stub_png(tmp_path)]):
        first = client_mock.post(f"/materials/{mat}/preview-chart", json=spec)
        second = client_mock.post(f"/materials/{mat}/preview-chart", json=spec)

    assert first.status_code == 200 and second.status_code == 200, second.text
    assert builds["n"] == 1, f"expected the second request to be cached, got {builds['n']}"
    assert first.headers.get("X-Chart-Empty") == "1"
    assert second.headers.get("X-Chart-Empty") == "1"
