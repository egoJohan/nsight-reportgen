"""Deleting a study's last dataset makes the study read-only for good.

Spec: docs/superpowers/specs/2026-09-24-dataset-deletion-design.md. Agreed with
Johan 2026-09-24: report definitions go, the decks already generated stay — the
study becomes what a Read-only user sees, for everyone, and nothing new can be
written to it.

Every delete here runs through `approve_all`: the in-memory store asks for
consent on each destructive step exactly as datahive does, so every test is
also a test of a delete interrupted after each step and called again.
"""
from __future__ import annotations

import json

import pytest

from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository, StudyReadOnly
from reportbuilder.store.seam import AuthContext, ConsentRequired, NotFound

pytestmark = pytest.mark.unit

DECK = b"PK\x03\x04 a generated deck"


def approve_all(store, fn):
    for _ in range(100):
        try:
            return fn()
        except ConsentRequired as exc:
            store.approve(exc.request_id)
    raise AssertionError("consent loop did not converge")


@pytest.fixture
def store():
    return InMemoryObjectStore()


@pytest.fixture
def repo(store):
    return Repository(store)


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def study(repo, auth):
    """A study with one dataset, one generated report and one never generated."""
    c = repo.create_customer(auth, "Acme")
    k = repo.create_case(auth, c.id, "Brändi 2026")
    m = repo.attach_material(auth, c.id, k.id, "brandi.sav", b"SAV")
    repo.save_material_config(auth, c.id, k.id, m.id, {"merges": ["x"]})
    done = repo.save_report(auth, c.id, k.id, json.dumps({"name": "Delivered"}))
    repo.save_render(auth, c.id, k.id, done.id, DECK,
                     repo.render_key(auth, c.id, k.id, done.id, m.id))
    draft = repo.save_report(auth, c.id, k.id, json.dumps({"name": "Draft"}))
    return c, k, m, done, draft


def _delete(repo, store, auth, c, k, m):
    return approve_all(store, lambda: repo.delete_material(
        auth, c.id, k.id, m.id, by="usr-1", by_name="Johan Wessberg"))


class TestTheLastDataset:
    def test_the_study_becomes_read_only_and_says_who_and_when(self, repo, store, auth, study):
        c, k, m, _done, _draft = study
        _delete(repo, store, auth, c, k, m)
        state = repo.get_case(auth, c.id, k.id).dataset_deleted
        assert state and state["completed"] is True
        assert state["by"] == "usr-1" and state["by_name"] == "Johan Wessberg"
        assert state["files"] == ["brandi.sav"] and state["at"]
        assert repo.find_case(auth, k.id).dataset_deleted == state

    def test_the_dataset_and_its_curation_are_gone(self, repo, store, auth, study):
        c, k, m, _done, _draft = study
        _delete(repo, store, auth, c, k, m)
        assert repo.list_materials(auth, c.id, k.id) == []
        assert repo.load_material_config(auth, c.id, k.id, m.id) == {}

    def test_a_generated_report_keeps_its_deck_and_loses_its_definition(
            self, repo, store, auth, study):
        c, k, m, done, _draft = study
        _delete(repo, store, auth, c, k, m)
        [ref] = repo.list_reports(auth, c.id, k.id)
        assert (ref.id, ref.name, ref.deck_only, ref.rendered) == (done.id, "Delivered", True, True)
        with pytest.raises(NotFound):
            repo.load_report(auth, c.id, k.id, done.id)
        assert repo.load_deck_only(auth, c.id, k.id, done.id) == DECK

    def test_a_report_never_generated_is_gone_entirely(self, repo, store, auth, study):
        c, k, m, _done, draft = study
        _delete(repo, store, auth, c, k, m)
        leftovers = [i.path for i in store.list(auth, P.reports_prefix(c.id, k.id))
                     if f"/{draft.id}" in i.path]
        assert leftovers == []

    def test_a_deck_older_than_later_edits_is_still_kept(self, repo, store, auth, study):
        """It is what was delivered; the definition it was drawn from is going anyway."""
        c, k, m, done, _draft = study
        repo.save_report(auth, c.id, k.id, json.dumps({"name": "Delivered", "edited": 1}),
                         report_id=done.id)
        _delete(repo, store, auth, c, k, m)
        assert [r.id for r in repo.list_reports(auth, c.id, k.id)] == [done.id]
        assert repo.load_deck_only(auth, c.id, k.id, done.id) == DECK

    def test_nothing_can_be_rendered_into_it_afterwards(self, repo, store, auth, study):
        """A render already running when the delete starts must save nothing."""
        c, k, m, done, _draft = study
        _delete(repo, store, auth, c, k, m)
        with pytest.raises(StudyReadOnly):
            repo.save_render(auth, c.id, k.id, done.id, b"PK late", "k")
        assert repo.load_deck_only(auth, c.id, k.id, done.id) == DECK

    def test_a_live_report_is_not_served_as_deck_only(self, repo, auth, study):
        c, k, _m, done, _draft = study
        assert repo.load_deck_only(auth, c.id, k.id, done.id) is None


class TestAnInterruptedDelete:
    def test_it_is_marked_unfinished_until_the_last_step(self, repo, store, auth, study, monkeypatch):
        c, k, m, _done, _draft = study
        original = repo._delete_material_objects

        def dies(*a, **kw):
            raise RuntimeError("process died")

        monkeypatch.setattr(repo, "_delete_material_objects", dies)
        with pytest.raises(RuntimeError):
            approve_all(store, lambda: repo.delete_material(auth, c.id, k.id, m.id))
        state = repo.get_case(auth, c.id, k.id).dataset_deleted
        assert state and state["completed"] is False

        monkeypatch.setattr(repo, "_delete_material_objects", original)
        _delete(repo, store, auth, c, k, m)
        assert repo.get_case(auth, c.id, k.id).dataset_deleted["completed"] is True
        assert repo.list_materials(auth, c.id, k.id) == []

    def test_resuming_after_the_dataset_is_already_gone_finishes(self, repo, store, auth, study):
        c, k, m, _done, _draft = study
        _delete(repo, store, auth, c, k, m)
        d = json.loads(store.get(auth, P.case_meta_path(c.id, k.id)).decode())
        d["dataset_deleted"]["completed"] = False
        store.put(auth, P.case_meta_path(c.id, k.id), json.dumps(d).encode(),
                  "application/json", [P.LABEL_CASE])
        _delete(repo, store, auth, c, k, m)
        assert repo.get_case(auth, c.id, k.id).dataset_deleted["completed"] is True


class TestOneOfSeveralDatasets:
    def test_only_that_file_goes_and_the_study_stays_live(self, repo, store, auth, study):
        c, k, m, done, draft = study
        newer = repo.attach_material(auth, c.id, k.id, "brandi-v2.sav", b"SAV2")
        _delete(repo, store, auth, c, k, m)
        assert repo.get_case(auth, c.id, k.id).dataset_deleted is None
        assert [x.id for x in repo.list_materials(auth, c.id, k.id)] == [newer.id]
        assert {r.id for r in repo.list_reports(auth, c.id, k.id)} == {done.id, draft.id}
        repo.load_report(auth, c.id, k.id, draft.id)


class TestTheWarningsFacts:
    def test_last_dataset(self, repo, auth, study):
        c, k, m, _done, _draft = study
        u = repo.dataset_usage(auth, c.id, k.id, m.id)
        assert u == {"last_dataset": True, "remaining": [],
                     "with_deck": ["Delivered"], "without_deck": ["Draft"]}

    def test_one_of_several_names_what_remains(self, repo, auth, study):
        c, k, m, _done, _draft = study
        repo.attach_material(auth, c.id, k.id, "brandi-v2.sav", b"SAV2")
        u = repo.dataset_usage(auth, c.id, k.id, m.id)
        assert u["last_dataset"] is False and u["remaining"] == ["brandi-v2.sav"]


def test_a_read_only_studys_decks_survive_backup_and_restore(repo, store, auth, study):
    """The whole-store backup leaves decks out because a live report can draw
    its deck again. A read-only study's decks are all that is left of it."""
    import io

    from reportbuilder.store import backup

    c, k, m, done, _draft = study
    _delete(repo, store, auth, c, k, m)
    buf = io.BytesIO()
    backup.write(repo, auth, buf)

    fresh_store = InMemoryObjectStore()
    fresh = Repository(fresh_store)
    approve_all(fresh_store, lambda: backup.read(fresh, auth, io.BytesIO(buf.getvalue())))
    assert [r.id for r in fresh.list_reports(auth, c.id, k.id)] == [done.id]
    assert fresh.load_deck_only(auth, c.id, k.id, done.id) == DECK
    assert fresh.get_case(auth, c.id, k.id).dataset_deleted["completed"] is True


class TestDecksNotKept:
    """"If there is deck/PDF downloadable, let's have a tick box whether to leave
    those or delete." (Johan, 2026-09-24) Unticked, nothing of the reports is
    left; the study is still read-only, now empty."""

    def test_every_report_and_deck_goes(self, repo, store, auth, study):
        c, k, m, done, _draft = study
        approve_all(store, lambda: repo.delete_material(
            auth, c.id, k.id, m.id, keep_decks=False))
        assert repo.list_reports(auth, c.id, k.id) == []
        assert list(store.list(auth, P.reports_prefix(c.id, k.id))) == []
        state = repo.get_case(auth, c.id, k.id).dataset_deleted
        assert state["completed"] is True and state["keep_decks"] is False

    def test_a_resumed_delete_keeps_to_the_choice_made(self, repo, store, auth, study, monkeypatch):
        c, k, m, done, _draft = study
        original = repo._delete_material_objects
        monkeypatch.setattr(repo, "_delete_material_objects",
                            lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("died")))
        with pytest.raises(RuntimeError):
            approve_all(store, lambda: repo.delete_material(
                auth, c.id, k.id, m.id, keep_decks=False))
        monkeypatch.setattr(repo, "_delete_material_objects", original)
        # Resumed WITHOUT saying — the recorded choice decides.
        approve_all(store, lambda: repo.delete_material(auth, c.id, k.id, m.id))
        assert repo.list_reports(auth, c.id, k.id) == []
        assert repo.load_deck_only(auth, c.id, k.id, done.id) is None
