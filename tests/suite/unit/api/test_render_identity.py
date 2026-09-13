"""An editor left open across a deploy learns that the server draws differently.

"Kuvassa olevat selitystekstit menevät välillä päällekkäin" — reported with a
picture of a chart fixed the day before: its bars carried no "(n=…)", which
every stacked bar has had since that morning's deploy, so it was drawn by the
code from before it. The server never serves such a picture: its preview cache
is keyed on a digest of its own source (`_PREVIEW_CACHE_SALT`), so a new image
is a new namespace. The EDITOR does: it holds each slide's picture for as long
as the slide is on screen, keyed on what the chart asks for and nothing about
who drew it. A tab opened before a deploy went on showing the old pictures.

So `/health` says which pictures this server draws, and the editor keys its
pictures on that too. (Johan, 2026-09-11)
"""
from __future__ import annotations

from fastapi.testclient import TestClient

import reportbuilder.api.routes_questions as RQ
from reportbuilder.api.server import create_app


def test_health_says_which_pictures_this_server_draws():
    body = TestClient(create_app()).get("/health").json()
    assert body["render_identity"] == RQ._PREVIEW_CACHE_SALT
    assert body["render_identity"]


def test_a_server_that_draws_differently_keeps_its_pictures_apart(monkeypatch):
    """The same chart on another build is another picture, on the server as in
    the editor — both follow the one identity."""
    spec = '{"chart_type":"stacked_horizontal_bar"}'
    before = RQ._preview_out_dir("mat-identity-test", spec)
    monkeypatch.setattr(RQ, "_PREVIEW_CACHE_SALT", "a-later-build")
    assert RQ._preview_out_dir("mat-identity-test", spec) != before


def test_a_delivered_deck_is_not_part_of_it(monkeypatch):
    """Decks are stored under `render_key`, which a deploy must NOT move — see
    test_regression_old_render_keys.py. Only previews follow the build."""
    from reportbuilder.store.memory_objects import InMemoryObjectStore
    from reportbuilder.store.repository import Repository
    from reportbuilder.store.seam import AuthContext

    auth = AuthContext(token="t")
    repo = Repository(InMemoryObjectStore())
    cust = repo.create_customer(auth, "Asiakas")
    case = repo.create_case(auth, cust.id, "Tutkimus")
    mat = repo.attach_material(auth, cust.id, case.id, "s.sav", b"data")
    rep = repo.save_report(auth, cust.id, case.id, '{"name":"R","charts":[]}')
    key = repo.render_key(auth, cust.id, case.id, rep.id, mat.id)
    monkeypatch.setattr(RQ, "_PREVIEW_CACHE_SALT", "a-later-build")
    assert repo.render_key(auth, cust.id, case.id, rep.id, mat.id) == key
