"""A preview does not re-download a template it already has on disk.

Opening a nine-slide report warm — every picture already drawn, nothing to
render — took 4.5s. None of it was rendering: each preview made 11 datahive
calls, and one of them pulled the whole 600KB template down again. Nine slides
is 5.4MB fetched for a file already sitting in the cache directory, all of it
queued against the hive container, which runs on one CPU.

The cached file is named for its CONTENT (`default.<sha256[:16]>.pptx`), so the
name could only be known by fetching the bytes. But the hive's listing already
reports an etag that IS that sha256, truncated:

    etag   9acac45c7ca729d1e08c732e2ece294a
    sha256 9acac45c7ca729d1e08c732e2ece294a9d1df44dc3babcf277a8ee555e93f044
    file   default.9acac45c7ca729d1.pptx

So the name is derivable from metadata alone. Same file, same guarantee — a
re-uploaded template has different bytes, so a different etag, so a different
name, and re-resolves exactly as it does today.

These tests count fetches rather than seconds: on a shared machine a timing
assertion proves nothing, while "did it pull the bytes" is the property that
was wrong. (Johan, 2026-09-16)
"""
from __future__ import annotations

import pathlib

import pytest

from reportbuilder.api import routes_questions as rq
from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.unit

AUTH = AuthContext(token="t")
BLOB = b"PK\x03\x04" + b"a template pretending to be a pptx" * 200


class CountingStore(InMemoryObjectStore):
    """Remembers which paths had their BYTES pulled."""

    def __init__(self):
        super().__init__()
        self.fetched: list[str] = []

    def get(self, auth, path):
        self.fetched.append(path)
        return super().get(auth, path)


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(rq.cache_dirs, "template_root", lambda: tmp_path)
    store = CountingStore()
    repo = Repository(store)
    cust = repo.create_customer(AUTH, "Asiakas")
    case = repo.create_case(AUTH, cust.id, "Tutkimus")
    mat = repo.attach_material(AUTH, cust.id, case.id, "s.sav", b"data")
    store.put(AUTH, P.default_template_path(), BLOB,
              content_type="application/vnd.openxmlformats-officedocument."
                           "presentationml.presentation")
    return repo, store, mat.id, tmp_path


def _template_fetches(store) -> list[str]:
    return [p for p in store.fetched if p.endswith(".pptx")]


def test_the_first_preview_fetches_and_caches_it(setup):
    """No assertion on WHICH hash names the file: datahive etags are a
    truncated sha256 and the in-memory store's are md5, so pinning one here
    would be testing the fixture's store rather than the behaviour. That
    different bytes give a different name is the property that matters, and
    `test_a_changed_template_is_picked_up` is where it is held."""
    repo, store, mat_id, tmp_path = setup
    path, _tid = rq._preview_template(repo, AUTH, mat_id)
    assert path is not None and _template_fetches(store)
    assert pathlib.Path(path).exists()
    assert pathlib.Path(path).parent == tmp_path
    assert pathlib.Path(path).read_bytes() == BLOB


def test_the_second_preview_does_not_fetch_it_again(setup):
    """The defect: nine slides pulled the same 600KB nine times."""
    repo, store, mat_id, _tmp = setup
    first, _ = rq._preview_template(repo, AUTH, mat_id)
    store.fetched.clear()
    second, _ = rq._preview_template(repo, AUTH, mat_id)
    assert second == first, "a second preview resolved a different file"
    assert not _template_fetches(store), (
        f"re-downloaded the template it already had: {_template_fetches(store)}")


def test_a_changed_template_is_picked_up(setup):
    """The guarantee that must survive: re-uploading different bytes must not
    keep rendering from the old file."""
    repo, store, mat_id, _tmp = setup
    first, _ = rq._preview_template(repo, AUTH, mat_id)
    store.put(AUTH, P.default_template_path(), BLOB + b"CHANGED",
              content_type="application/vnd.openxmlformats-officedocument."
                           "presentationml.presentation")
    second, _ = rq._preview_template(repo, AUTH, mat_id)
    assert second != first, "kept the old template after a re-upload"


def test_a_missing_cached_file_is_fetched_again(setup):
    """Someone cleared the cache directory; the preview must still work."""
    repo, store, mat_id, tmp_path = setup
    first, _ = rq._preview_template(repo, AUTH, mat_id)
    for f in tmp_path.glob("*.pptx"):
        f.unlink()
    store.fetched.clear()
    again, _ = rq._preview_template(repo, AUTH, mat_id)
    assert again == first
    assert _template_fetches(store), "did not re-fetch after the file vanished"
