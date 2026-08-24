"""The template copy a preview renders from is never seen half written.

Previews run concurrently — after a template switch the whole deck is queued at
once — and every one of them wants the same template file on disk. Written in
place, the first request creates it and the rest find it existing and parse it
half finished. python-pptx raises, the route's guard turns that into "no
template", and the slide renders in HOUSE STYLE — which is then cached under a
key that says it IS this template, so it stays wrong until something else moves.

Driven through `_preview_template` itself rather than by repeating what it does,
so reverting it to a plain write fails this.
"""
from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pytest

from reportbuilder.api import routes_questions as rq

BLOB = b"PK\x03\x04" + b"x" * 200_000


@dataclass
class _Material:
    id: str = "mat-1"
    customer_id: str = "cust-1"
    case_id: str = "case-1"


class _Repo:
    """Just enough repository for the template lookup."""

    def find_material(self, auth, material_id, **kw):
        return _Material()

    def resolve_template(self, auth, customer_id, case_id, report_id):
        return "tpl-1", "case"

    def get_template_bytes(self, auth, customer_id, template_id):
        return BLOB


@pytest.fixture
def temp_root(tmp_path, monkeypatch):
    import tempfile

    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path / "nsight-preview-templates"


def test_the_published_path_never_holds_a_partial_file(temp_root, monkeypatch):
    """Look for a published template halfway through writing one.

    Every other reader of this directory is doing exactly that, just without the
    instrumentation: it opens the path as soon as it exists.
    """
    published_mid_write: list[tuple[bool, int]] = []
    target_name = rq._preview_template_filename("tpl-1", BLOB)
    real_write_bytes = pathlib.Path.write_bytes

    def halfway(self: pathlib.Path, data: bytes):
        real_write_bytes(self, data[: len(data) // 2])
        target = self.parent / target_name
        published_mid_write.append(
            (target.exists(), target.stat().st_size if target.exists() else 0))
        with open(self, "ab") as fh:
            fh.write(data[len(data) // 2:])
        return len(data)

    monkeypatch.setattr(pathlib.Path, "write_bytes", halfway)

    path, template_id = rq._preview_template(_Repo(), object(), "mat-1")

    assert published_mid_write, "the write never happened — the test proved nothing"
    assert published_mid_write == [(False, 0)], (
        "a reader could have parsed a half-written template: "
        f"{published_mid_write}")
    assert template_id == "tpl-1"
    assert pathlib.Path(path).read_bytes() == BLOB


def test_it_leaves_nothing_behind(temp_root):
    path, _ = rq._preview_template(_Repo(), object(), "mat-1")
    assert [p.name for p in pathlib.Path(path).parent.iterdir()] == [
        pathlib.Path(path).name], "a leftover .part is a file the next scan finds"


def test_a_second_request_reuses_the_file_rather_than_rewriting_it(temp_root,
                                                                  monkeypatch):
    first, _ = rq._preview_template(_Repo(), object(), "mat-1")
    writes = {"n": 0}
    real_write_bytes = pathlib.Path.write_bytes

    def counting(self: pathlib.Path, data: bytes):
        writes["n"] += 1
        return real_write_bytes(self, data)

    monkeypatch.setattr(pathlib.Path, "write_bytes", counting)
    second, _ = rq._preview_template(_Repo(), object(), "mat-1")
    assert second == first
    assert writes["n"] == 0
