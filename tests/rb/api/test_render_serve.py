"""Tests for deterministic render output dir and GET /cases/.../preview.pdf.
(REQ-C-19, REQ-C-21)

The render routes are `require_case`/`require_case_write` guarded: the case_id
in the path is resolved through the repository before the handler runs, so a
test addressing a real render needs a real, repository-known case id. The
"not rendered" 404 tests deliberately use ids nothing seeded — the guard 404s
on those too, just for a different reason ("no such case" rather than "no
file on disk"), and either is a legitimate 404 for this assertion.
"""
from __future__ import annotations

import tempfile
from unittest.mock import Mock, patch

from reportbuilder.api.routes_render import render_output_dir


# ---------------------------------------------------------------------------
# Test 1 — render_output_dir is deterministic and under tempdir (REQ-C-19)
# ---------------------------------------------------------------------------


def test_render_output_dir_deterministic() -> None:
    """render_output_dir returns the same path for the same ids and is under tempdir. (REQ-C-19)"""
    d1 = render_output_dir("c1", "r1")
    d2 = render_output_dir("c1", "r1")
    assert d1 == d2
    assert str(d1).startswith(tempfile.gettempdir())
    assert d1.exists()


def test_render_output_dir_sanitises_ids() -> None:
    """render_output_dir sanitises special chars out of ids, preventing path traversal. (REQ-C-19)"""
    d = render_output_dir("case/../../etc", "rep;rm -rf /")
    # Path must remain under the nsight-render subdir (no traversal)
    assert str(d).startswith(tempfile.gettempdir())
    # Must exist (mkdir succeeded with sanitised path)
    assert d.exists()


# ---------------------------------------------------------------------------
# Test 2 — GET /cases/.../preview.pdf returns PDF bytes (REQ-C-21)
# ---------------------------------------------------------------------------


def test_get_preview_pdf_returns_file(rb_wire) -> None:
    """GET preview.pdf for a rendered report streams the PDF bytes with correct content-type.
    (REQ-C-21)"""
    http = rb_wire(client=Mock())

    # Write a dummy PDF into the deterministic dir
    pdf_path = render_output_dir(http.case_id, "r1") / "deck.pdf"
    pdf_path.write_bytes(b"%PDF-dummy")

    try:
        resp = http.get(f"/cases/{http.case_id}/reports/r1/preview.pdf")
    finally:
        pdf_path.unlink(missing_ok=True)

    assert resp.status_code == 200
    assert "application/pdf" in resp.headers["content-type"]
    assert resp.content == b"%PDF-dummy"


# ---------------------------------------------------------------------------
# Test 3 — GET preview.pdf for an unrendered report → 404 (REQ-C-21)
# ---------------------------------------------------------------------------


def test_get_preview_pdf_404_when_not_rendered(rb_wire) -> None:
    """GET preview.pdf for an unrendered report returns 404. (REQ-C-21)"""
    http = rb_wire(client=Mock())

    # Neither id is known to the repository or has a PDF on disk.
    resp = http.get("/cases/never-rendered-xxxx/reports/never-rendered-yyyy/preview.pdf")

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Test 4 — POST render response includes pdf_url (REQ-C-19)
# ---------------------------------------------------------------------------

_ARTIFACTS = {
    "pptx": "/t/deck.pptx",
    "pdf": "/t/deck.pdf",
    "preview": ["/t/p1.png"],
}


def test_render_response_includes_pdf_url(rb_wire) -> None:
    """POST render response includes pdf_url pointing to the GET preview route. (REQ-C-19)"""
    http = rb_wire(client=Mock())

    with patch("reportbuilder.api.routes_render.orchestrate_render") as mock_orch:
        mock_orch.return_value = dict(_ARTIFACTS)

        resp = http.post(
            f"/cases/{http.case_id}/reports/r2/render",
            json={"material_id": "mat-1"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["pdf_url"] == f"/cases/{http.case_id}/reports/r2/preview.pdf"
    # Render dir was passed to orchestrate
    call_kwargs = mock_orch.call_args[1]
    assert "out_dir" in call_kwargs
    assert call_kwargs["out_dir"].endswith(f"/{http.case_id}/r2")


# ---------------------------------------------------------------------------
# Test 5 — GET /cases/.../preview.pptx returns PPTX bytes
# ---------------------------------------------------------------------------


def test_get_preview_pptx_returns_file(rb_wire) -> None:
    """GET preview.pptx for a rendered report streams bytes with the correct PPTX content-type."""
    http = rb_wire(client=Mock())

    # Write a dummy PPTX into the deterministic dir
    pptx_path = render_output_dir(http.case_id, "r3") / "deck.pptx"
    pptx_path.write_bytes(b"PK\x03\x04dummy-pptx")

    try:
        resp = http.get(f"/cases/{http.case_id}/reports/r3/preview.pptx")
    finally:
        pptx_path.unlink(missing_ok=True)

    assert resp.status_code == 200
    assert (
        "openxmlformats-officedocument.presentationml.presentation"
        in resp.headers["content-type"]
    )
    assert resp.content == b"PK\x03\x04dummy-pptx"


# ---------------------------------------------------------------------------
# Test 6 — GET preview.pptx for an unrendered report → 404
# ---------------------------------------------------------------------------


def test_get_preview_pptx_404_when_not_rendered(rb_wire) -> None:
    """GET preview.pptx for an unrendered report returns 404."""
    http = rb_wire(client=Mock())

    resp = http.get("/cases/never-pptx-xxxx/reports/never-pptx-yyyy/preview.pptx")

    assert resp.status_code == 404
