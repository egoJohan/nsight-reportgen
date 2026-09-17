"""The author warnings are reported on the path the Design page actually uses.

Both header tests drove the LibreOffice branch — measured: 6 of 6 previews, with
`compose_from_slide` never called. They omit `render_title`, which defaults to
True, and the route composites only when it is False, which is exactly how the
Design page asks. So `_record_empty` and `_record_unlabelled` could have been
dropped from the fast branch entirely and every test would have passed, while
every warning an author could actually see stopped working.

The branch is the subject here, so the render is stubbed at its seam: a
compositor that returns a picture, and a builder that reports what a real one
would. The RULES behind the two warnings are covered elsewhere against real
matplotlib output — test_too_many_categories_to_label and
test_empty_chart_is_reported_to_the_author. (Johan, 2026-09-17)
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
        # The Design page's own request, and the ONLY way the compositor runs.
        "render_title": False,
    }
    body.update(overrides)
    return body


def _a_picture():
    from PIL import Image
    return Image.new("RGB", (8, 8), (255, 255, 255))


def _reporting(*, empty=False, unlabelled=0):
    """Stands in for the deck builder, reporting what a real one would."""
    from reportbuilder.render.base import RenderNote

    def build(*a, empty_out=None, notes=None, **k):
        if empty and empty_out is not None:
            empty_out.append("q1")
        if unlabelled and notes is not None:
            notes.append(RenderNote(kind="unlabelled", count=unlabelled))

        class _Prs:
            slides = [object()]
        return _Prs()
    return build


def _preview(client, spec, **flags):
    with patch(f"{_RQ}.build_presentation", side_effect=_reporting(**flags)), \
         patch(f"{_RQ}.compose_from_slide", return_value=_a_picture()):
        return client.post(f"/materials/{client.material_id}/preview-chart",
                           json=spec)


def test_the_fast_path_is_the_one_under_test(client_mock):
    """Without this the rest could pass by quietly falling back, which is how
    the gap arose in the first place."""
    r = _preview(client_mock, _spec())
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Preview-Path") == "composited"


def test_a_blank_chart_says_so_on_the_fast_path(client_mock):
    r = _preview(client_mock, _spec(template_slot="s2"), empty=True)
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Chart-Empty") == "1"


def test_an_unlabelled_chart_says_so_on_the_fast_path(client_mock):
    r = _preview(client_mock, _spec(template_slot="s3"), unlabelled=25)
    assert r.status_code == 200, r.text
    assert r.headers.get("X-Chart-Unlabelled") == "25"


def test_an_ordinary_chart_says_nothing_on_the_fast_path(client_mock):
    r = _preview(client_mock, _spec(template_slot="s4"))
    assert r.status_code == 200, r.text
    assert "X-Chart-Empty" not in r.headers
    assert "X-Chart-Unlabelled" not in r.headers


def test_the_cached_fast_preview_still_says_it(client_mock):
    """The cache hit returns before any rendering, on this path too."""
    builds = {"n": 0}
    report = _reporting(empty=True, unlabelled=25)

    def counting(*a, **k):
        builds["n"] += 1
        return report(*a, **k)

    spec = _spec(template_slot="s5")
    with patch(f"{_RQ}.build_presentation", side_effect=counting), \
         patch(f"{_RQ}.compose_from_slide", return_value=_a_picture()):
        first = client_mock.post(
            f"/materials/{client_mock.material_id}/preview-chart", json=spec)
        second = client_mock.post(
            f"/materials/{client_mock.material_id}/preview-chart", json=spec)

    assert first.status_code == 200 and second.status_code == 200, second.text
    assert builds["n"] == 1, f"expected the second to be cached, got {builds['n']}"
    for r in (first, second):
        assert r.headers.get("X-Chart-Empty") == "1"
        assert r.headers.get("X-Chart-Unlabelled") == "25"
