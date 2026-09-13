"""A preview says which rasteriser drew it.

Two different programs draw a preview. The fast path composites the chart onto
a cached picture of the customer's empty slide (PIL); the fallback runs the
whole deck through LibreOffice. They are 10-20x apart in cost and they do not
produce identical pixels, so "which one drew this" is not a curiosity — it is
the difference between a picture you can compare against a baseline and one you
cannot.

Today nothing says. `X-Title-Box` is present only on the fast path, but its
ABSENCE means any of: fell back to LibreOffice / the caller asked for a baked
title / no template / a template whose profile states no positioned title box.
The last of those renders correctly on the fast path and carries no header, so
a gate asserting on it would redden a correct render.

So the route says so itself. (Johan, 2026-09-12)
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


def test_a_preview_drawn_by_libreoffice_says_libreoffice(client_mock, tmp_path):
    """The render chain is stubbed, so this asserts the ROUTE's report of which
    path it took — not LibreOffice itself, which is not installed here."""
    with patch(f"{_RQ}.shutil.which", return_value="soffice"), \
         patch(f"{_RQ}.build_pptx"), \
         patch(f"{_RQ}.pptx_to_pdf", return_value=str(tmp_path / "d.pdf")), \
         patch(f"{_RQ}.rasterize_pages", return_value=[_stub_png(tmp_path)]):
        r = client_mock.post(
            f"/materials/{client_mock.material_id}/preview-chart",
            json=_spec(),          # render_title defaults True -> LibreOffice
        )

    assert r.status_code == 200, r.text
    assert r.headers.get("X-Preview-Path") == "libreoffice"


def test_a_cached_preview_reports_the_path_that_actually_drew_it(client_mock, tmp_path):
    """The cache hit returns BEFORE any rendering, so it cannot know which path
    drew the bytes it is serving — it has to have been told.

    Guessing here would be worse than saying nothing: the acceptance run asserts
    every case is `composited`, and a cached picture that LibreOffice actually
    drew would pass that assertion while being a different rasteriser's output.
    """
    builds = {"n": 0}

    def counting_build(*a, **k):
        builds["n"] += 1

    spec = _spec()
    mat = client_mock.material_id
    with patch(f"{_RQ}.shutil.which", return_value="soffice"), \
         patch(f"{_RQ}.build_pptx", side_effect=counting_build), \
         patch(f"{_RQ}.pptx_to_pdf", return_value=str(tmp_path / "d.pdf")), \
         patch(f"{_RQ}.rasterize_pages", return_value=[_stub_png(tmp_path)]):
        first = client_mock.post(f"/materials/{mat}/preview-chart", json=spec)
        second = client_mock.post(f"/materials/{mat}/preview-chart", json=spec)

    assert first.status_code == 200 and second.status_code == 200, second.text
    # Without this the test could pass by never reaching the cache at all.
    assert builds["n"] == 1, f"expected the second request to be cached, got {builds['n']} renders"
    assert first.headers.get("X-Preview-Path") == "libreoffice"
    assert second.headers.get("X-Preview-Path") == "libreoffice"


@pytest.mark.export
def test_a_composited_preview_says_composited(client_memory, synthetic_bytes,
                                              require_soffice):
    """The one the gate rests on.

    The acceptance run asserts every case is `composited`; a `libreoffice`
    reading means a ground build failed and the picture came from a different
    rasteriser. This needs a real template and a real ground, so unlike its
    neighbours it cannot be stubbed — the fast path is only taken when there is
    a cached empty slide to draw onto.
    """
    from reportbuilder.render.default_template import default_template_bytes

    cid = client_memory.post("/customers", json={"name": "Asiakas"}).json()["id"]
    kid = client_memory.post(f"/customers/{cid}/cases",
                             json={"name": "Tutkimus"}).json()["id"]
    mat = client_memory.post(
        f"/cases/{kid}/materials",
        files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
    ).json()["material_id"]
    up = client_memory.post(
        f"/customers/{cid}/templates",
        files={"file": ("pohja.pptx", default_template_bytes(),
                        "application/vnd.openxmlformats-officedocument."
                        "presentationml.presentation")},
    )
    assert up.status_code == 201, up.text
    qid = client_memory.get(f"/materials/{mat}/questions").json()["questions"][0]["qid"]

    r = client_memory.post(
        f"/materials/{mat}/preview-chart",
        # render_title=False is what the Design page sends, and the only way
        # the compositor is used at all.
        json=_spec(question_ref=qid, render_title=False,
                   template_id=up.json()["id"]),
    )

    assert r.status_code == 200, r.text
    assert r.content[:4] == b"\x89PNG"
    assert r.headers.get("X-Preview-Path") == "composited", (
        "the fast path drew this but did not say so; the gate cannot tell it "
        "from a LibreOffice fallback")
