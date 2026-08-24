"""REGRESSION: every deck rendered before this release becomes undownloadable.

`render_key` gained a fifth component (the resolved template's CONTENT), so the
key computed today can never equal the one the previous release stamped onto a
report's sidecar. `load_render` returns None on a key mismatch, and
routes_render._restore_deck turns that into `404 not rendered yet` — while the
sidecar still carries `render_key`, which is what `ReportRef.rendered` reads, so
the report goes on showing the Generated badge and offering the download.

On a fresh container (every deploy) /tmp holds no decks, so the FIRST download
of any already-rendered report after this release 404s.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def world():
    auth = AuthContext(token="t")
    repo = Repository(InMemoryObjectStore())
    cust = repo.create_customer(auth, "Asiakas")
    case = repo.create_case(auth, cust.id, "Tutkimus")
    mat = repo.attach_material(auth, cust.id, case.id, "s.sav", b"data")
    rep = repo.save_report(auth, cust.id, case.id, '{"name":"R","charts":[]}')
    return repo, auth, cust.id, case.id, rep.id, mat.id


def _key_as_the_previous_release_computed_it(repo, auth, cust, case, rid, mid):
    """render_key with its four pre-release components, verbatim."""
    from reportbuilder.render.fonts import rendering_fingerprint

    h = hashlib.sha256()
    for part in (
        repo.load_report(auth, cust, case, rid),
        json.dumps(repo.load_material_config(auth, cust, case, mid), sort_keys=True),
        mid,
        rendering_fingerprint(),
    ):
        h.update(part.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def test_a_deck_rendered_by_the_previous_release_is_still_downloadable(world):
    repo, auth, cust, case, rid, mid = world
    old = _key_as_the_previous_release_computed_it(repo, auth, cust, case, rid, mid)
    repo.save_render(auth, cust, case, rid, b"the delivered deck", old)

    # Nothing about the report, the data or the template has changed.
    ref = next(r for r in repo.list_reports(auth, cust, case) if r.id == rid)
    assert ref.rendered is True, "the UI shows the Generated badge and a download"

    blob = repo.load_render(auth, cust, case, rid,
                            repo.render_key(auth, cust, case, rid, mid))
    assert blob == b"the delivered deck", (
        "the download button offers a deck the backend will answer 404 for")
