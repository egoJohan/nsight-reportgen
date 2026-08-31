"""Integration tests for the RENDER API (routes_render).

Covers:
  - POST /cases/{cid}/reports/{rid}/render            (orchestrated export)
  - GET  /cases/{cid}/reports/{rid}/preview.pdf|pptx  (stream artifacts)
  - render_output_dir(case_id, report_id)             (deterministic + sanitized)

The stacked-no-classifying 422 guard and the artifact-404-before-render behavior
are soffice-FREE (they raise before / independently of LibreOffice). The FULL
happy-path render (build_pptx → pptx_to_pdf → rasterize) is `@pytest.mark.export`
+ `require_soffice`.

`client_memory` is a real local-fs InMemoryDataHive; we drive the true product
flow: create case → upload material → create report → render.
"""
from __future__ import annotations

import json
import shutil
import threading
from unittest.mock import patch

import pytest

from reportbuilder.api.routes_render import render_output_dir
from reportbuilder.model.report import (
    ChartSpec,
    ElementToggles,
    NumberFormat,
    Report,
    SortSpec,
    report_to_json,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report_json(chart_type: str, *, classifying_var=None,
                      question_ref: str = "q1") -> dict:
    """A valid single-chart report definition as a JSON-ready dict."""
    spec = ChartSpec(
        question_ref=question_ref, chart_type=chart_type, statistic="pct",
        classifying_var=classifying_var, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1",
        elements=ElementToggles(),
    )
    report = Report(name="R", render_mode="native", template_ref="",
                    charts=(spec,))
    return json.loads(report_to_json(report))


def _seed_case_material_report(client, chart_type: str, *,
                               classifying_var=None) -> tuple[str, str, str]:
    """Create a case, upload the synthetic SAV, and create a report with one
    chart. Returns (case_id, report_id, material_id)."""
    from reportbuilder.testing.fixtures import synthetic_sav_bytes

    cust = client.post("/customers", json={"name": "C"}).json()["id"]
    cid = client.post(f"/customers/{cust}/cases", json={"name": "C"}).json()["id"]
    up = client.post(
        f"/cases/{cid}/materials",
        files={"file": ("t.sav", synthetic_sav_bytes(),
                        "application/octet-stream")},
    ).json()
    mid = up["material_id"]
    rid = client.post(
        f"/cases/{cid}/reports",
        json=_make_report_json(chart_type, classifying_var=classifying_var),
    ).json()["report_id"]
    return cid, rid, mid


# ---------------------------------------------------------------------------
# render_output_dir helper
# ---------------------------------------------------------------------------


def test_render_output_dir_is_deterministic():
    a = render_output_dir("case-1", "report-1")
    b = render_output_dir("case-1", "report-1")
    assert a == b
    assert a.name == "report-1" and a.parent.name == "case-1"


def test_render_output_dir_sanitizes_path_traversal():
    """Traversal segments in ids must not escape the base dir."""
    d = render_output_dir("../evil", "../../etc")
    assert ".." not in d.parts
    # Only alnum/-/_ survive sanitisation, so a bare-dots component collapses.
    assert d.parent.name == "evil"
    # The whole path stays under the render cache root.
    from reportbuilder import cache_dirs
    assert d.is_relative_to(cache_dirs.render_root())


# ---------------------------------------------------------------------------
# Artifact streaming — 404 before any render exists
# ---------------------------------------------------------------------------


def test_preview_pdf_404_before_render(client_memory):
    cid, rid, _mid = _seed_case_material_report(client_memory, "vertical_bar")
    # render_output_dir is a deterministic dir in a shared temp root; a prior
    # export run may have left artifacts under the reused (case-1/report-1) ids,
    # so clear it to genuinely assert the pre-render state.
    shutil.rmtree(render_output_dir(cid, rid), ignore_errors=True)
    r = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pdf")
    assert r.status_code == 404


def test_preview_pptx_404_before_render(client_memory):
    cid, rid, _mid = _seed_case_material_report(client_memory, "vertical_bar")
    shutil.rmtree(render_output_dir(cid, rid), ignore_errors=True)
    r = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pptx")
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Stacked-no-classifying guard on render (soffice-free — raises before build)
# ---------------------------------------------------------------------------


def test_render_stacked_without_classifying_var_not_blocked(client_memory):
    """A non-battery stacked chart with no classifying variable is a valid
    total-only distribution — the render must NOT be rejected with a
    'classifying variable' 422 (holds with or without LibreOffice)."""
    cid, rid, mid = _seed_case_material_report(
        client_memory, "stacked_vertical_bar", classifying_var=None,
    )
    r = client_memory.post(
        f"/cases/{cid}/reports/{rid}/render",
        json={"material_id": mid, "view": "slides"},
    )
    assert not (r.status_code == 422
                and "classifying variable" in r.json().get("detail", "").lower()), (
        f"total-only stacked render must no longer be blocked: {r.text[:200]}"
    )


# ---------------------------------------------------------------------------
# Explicit cancel (replaces the old client-disconnect trigger) + render status
# + one render per report at a time
# ---------------------------------------------------------------------------


def _blocking_build(reached: threading.Event, released: threading.Event):
    """A build_pptx stand-in that stalls until the test releases it, so the
    test can observe/act on the render while it is genuinely in progress."""

    def _build(report, model, df, path, style=None, cancel_check=None):
        reached.set()
        released.wait(timeout=5)
        if cancel_check is not None and cancel_check():
            from reportbuilder.render.deck import RenderCancelled
            raise RenderCancelled()
        with open(path, "w") as f:
            f.write("pptx")
        return path

    return _build


def test_render_status_is_false_before_and_after_a_render(client_memory):
    cid, rid, mid = _seed_case_material_report(client_memory, "vertical_bar")
    idle = client_memory.get(f"/cases/{cid}/reports/{rid}/render/status")
    assert idle.status_code == 200
    assert idle.json() == {"rendering": False}


def test_render_cancel_stops_a_running_render_and_status_reflects_it(client_memory):
    """POST .../render/cancel sets the between-slides flag a running render
    watches — the same flag that used to get set by the client disconnecting.
    Nothing about the render disconnecting/navigating away is involved here."""
    cid, rid, mid = _seed_case_material_report(client_memory, "vertical_bar")
    reached, released = threading.Event(), threading.Event()

    outcome: dict = {}

    def _do_render():
        outcome["response"] = client_memory.post(
            f"/cases/{cid}/reports/{rid}/render", json={"material_id": mid})

    with patch("reportbuilder.api.routes_render.build_pptx",
               side_effect=_blocking_build(reached, released)):
        t = threading.Thread(target=_do_render)
        t.start()
        try:
            assert reached.wait(timeout=5), "render never reached build_pptx"

            # In progress, and the status route says so — this is the fact a
            # returning browser reads, not anything held in React state.
            status = client_memory.get(f"/cases/{cid}/reports/{rid}/render/status")
            assert status.json() == {"rendering": True}

            cancel = client_memory.post(f"/cases/{cid}/reports/{rid}/render/cancel")
            assert cancel.status_code == 200
            assert cancel.json() == {"cancelled": True}
        finally:
            released.set()
            t.join(timeout=5)

    assert outcome["response"].status_code == 499

    status = client_memory.get(f"/cases/{cid}/reports/{rid}/render/status")
    assert status.json() == {"rendering": False}

    # Pressing Cancel again once nothing is running is not an error — it just
    # did not have anything to stop.
    again = client_memory.post(f"/cases/{cid}/reports/{rid}/render/cancel")
    assert again.status_code == 200
    assert again.json() == {"cancelled": False}


def test_second_render_of_same_report_is_refused_while_one_is_running(client_memory):
    """Two renders of the same report racing to publish the same deck.pptx is
    the failure mode to avoid — a second POST while one is running is refused
    (409), not silently started alongside the first."""
    cid, rid, mid = _seed_case_material_report(client_memory, "vertical_bar")
    reached, released = threading.Event(), threading.Event()

    outcome: dict = {}

    def _do_render():
        outcome["response"] = client_memory.post(
            f"/cases/{cid}/reports/{rid}/render", json={"material_id": mid})

    def _fake_pdf_parallel(pptx_path, out_dir):
        import os
        pdf = os.path.join(out_dir, "work.pdf")
        with open(pdf, "w") as f:
            f.write("pdf")
        return pdf

    with (
        patch("reportbuilder.api.routes_render.build_pptx",
             side_effect=_blocking_build(reached, released)),
        patch("reportbuilder.api.routes_render.pptx_to_pdf_parallel",
             side_effect=_fake_pdf_parallel),
        # The real conversion never ran (the fake above wrote a placeholder,
        # not a real PDF), so the completion log line's page count would shell
        # out to pdfinfo on that placeholder and fail — irrelevant to what
        # this test checks.
        patch("reportbuilder.api.routes_render.pdf_page_count", return_value=0),
    ):
        t = threading.Thread(target=_do_render)
        t.start()
        try:
            assert reached.wait(timeout=5), "first render never reached build_pptx"

            second = client_memory.post(
                f"/cases/{cid}/reports/{rid}/render", json={"material_id": mid})
            assert second.status_code == 409
        finally:
            released.set()
            t.join(timeout=5)

    assert outcome["response"].status_code == 200


# ---------------------------------------------------------------------------
# Full happy-path render (needs real LibreOffice) — export-gated
# ---------------------------------------------------------------------------


@pytest.mark.export
def test_render_happy_path_returns_artifacts(client_memory, require_soffice):
    """A valid report renders end-to-end: response carries pptx/pdf/preview/
    pdf_url, and the streamed preview.pdf/pptx then resolve (200)."""
    cid, rid, mid = _seed_case_material_report(client_memory, "vertical_bar")
    r = client_memory.post(
        f"/cases/{cid}/reports/{rid}/render",
        json={"material_id": mid, "view": "slides"},
    )
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) >= {"pptx", "pdf", "pdf_url"}
    assert body["pdf_url"] == f"/cases/{cid}/reports/{rid}/preview.pdf"
    # No per-slide images at all: the app draws the deck from the PDF, and
    # rasterizing 60 PNGs nobody fetches cost ~7s and ~7 MB of tmpfs a render.
    assert "preview" not in body

    # Artifacts are now fetchable.
    pdf = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content[:4] == b"%PDF"

    pptx = client_memory.get(f"/cases/{cid}/reports/{rid}/preview.pptx")
    assert pptx.status_code == 200
    # PPTX is a zip container → starts with the "PK" local-file-header magic.
    assert pptx.content[:2] == b"PK"


@pytest.mark.export
def test_a_render_leaves_only_the_deck_and_its_pdf(client_memory, require_soffice,
                                                   tmp_path):
    """What a render leaves in /tmp matters: on most hosts /tmp is tmpfs, so
    every stray artifact is RAM. Each render used to add another ~7 MB of page
    images that nothing read."""
    import pathlib as _pathlib

    cid, rid, mid = _seed_case_material_report(client_memory, "vertical_bar")
    r = client_memory.post(f"/cases/{cid}/reports/{rid}/render",
                           json={"material_id": mid})
    assert r.status_code == 200
    out = _pathlib.Path(r.json()["pdf"]).parent
    left = sorted(p.name for p in out.iterdir())
    assert [n for n in left if n.startswith("pages-")] == []
    assert {"deck.pptx", "deck.pdf"} <= set(left)
