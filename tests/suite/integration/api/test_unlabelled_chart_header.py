"""A preview whose chart was too dense to label says how many categories.

The value labels are dropped when a bar is under 5pt tall — right, because a
label there would overlap its neighbours — but the author was never told, and
the same chart labels perfectly on a taller chart area. So the render records it
and the response carries it: `X-Chart-Unlabelled: 25`.

It rides beside `X-Chart-Empty` and is persisted the same way, for the same
reason: a cache hit returns before any rendering and cannot work it out.
(Johan, 2026-09-16)
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.integration

_RQ = "reportbuilder.api.routes_questions"


def _spec(**overrides) -> dict:
    body = {
        "question_ref": "q1",
        "chart_type": "horizontal_bar",
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


def _build_noting(kind: str | None, count: int = 0):
    """A stand-in builder that raises the note the real one would.

    The render chain is stubbed here as in its neighbours; the RULE — which
    charts are too dense to label — is covered against a real matplotlib render
    in test_too_many_categories_to_label.
    """
    from reportbuilder.render.base import RenderNote

    def build(*a, notes=None, **k):
        if kind and notes is not None:
            notes.append(RenderNote(kind=kind, count=count))
    return build


def test_a_chart_that_lost_its_numbers_says_how_many(client_mock, tmp_path):
    with patch(f"{_RQ}.shutil.which", return_value="soffice"), \
         patch(f"{_RQ}.build_pptx", side_effect=_build_noting("unlabelled", 25)), \
         patch(f"{_RQ}.pptx_to_pdf", return_value=str(tmp_path / "d.pdf")), \
         patch(f"{_RQ}.rasterize_pages", return_value=[_stub_png(tmp_path)]):
        r = client_mock.post(f"/materials/{client_mock.material_id}/preview-chart",
                             json=_spec())

    assert r.status_code == 200, r.text
    assert r.headers.get("X-Chart-Unlabelled") == "25"


def test_an_ordinary_chart_says_nothing(client_mock, tmp_path):
    with patch(f"{_RQ}.shutil.which", return_value="soffice"), \
         patch(f"{_RQ}.build_pptx", side_effect=_build_noting(None)), \
         patch(f"{_RQ}.pptx_to_pdf", return_value=str(tmp_path / "d.pdf")), \
         patch(f"{_RQ}.rasterize_pages", return_value=[_stub_png(tmp_path)]):
        r = client_mock.post(f"/materials/{client_mock.material_id}/preview-chart",
                             json=_spec(template_slot="s2"))

    assert r.status_code == 200, r.text
    assert "X-Chart-Unlabelled" not in r.headers


def test_the_cached_preview_says_it_too(client_mock, tmp_path):
    builds = {"n": 0}
    noting = _build_noting("unlabelled", 25)

    def counting(*a, **k):
        builds["n"] += 1
        noting(*a, **k)

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
    assert first.headers.get("X-Chart-Unlabelled") == "25"
    assert second.headers.get("X-Chart-Unlabelled") == "25"
