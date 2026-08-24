"""Three editors, one config object.

Renaming a question, merging words and marking a classifier all live in the
same per-material curation blob, and each one loaded the WHOLE thing, changed
its own corner and wrote it back. Two at once and the second write puts back
what it read before the first: the rename lands, the merge lands, and one of
them is silently gone. Nothing reports it — the analyst finds out later when
the label they set is not there.
"""
from __future__ import annotations

import threading

import pytest

from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def material():
    auth = AuthContext(token="t")
    repo = Repository(InMemoryObjectStore())
    cust = repo.create_customer(auth, "Asiakas")
    case = repo.create_case(auth, cust.id, "Tutkimus")
    mat = repo.attach_material(auth, cust.id, case.id, "s.sav", b"data")
    return repo, auth, cust.id, case.id, mat.id


def test_two_editors_do_not_lose_each_others_work(material):
    """Deterministic, not hopeful.

    Timing alone made this pass against the bug about one run in five: without
    the lock the two threads have to interleave in a particular way to lose a
    write, and often they simply do not. So the first reader is HELD until the
    second has read — the exact interleaving the lock exists to prevent — by
    stalling inside the mutate callback, which runs between the read and the
    write.
    """
    repo, auth, cust, case, mat = material
    both_have_read = threading.Barrier(2, timeout=5)

    def rename(cfg):
        # Both threads reach here having each read the config. Without the
        # lock, that is two readers holding the same snapshot; with it, the
        # second thread cannot get here until the first has written, and the
        # barrier times out — which is the point, so it is caught below.
        try:
            both_have_read.wait()
        except threading.BrokenBarrierError:
            pass
        cfg["question_labels"] = {"q1": "Renamed"}
        return cfg

    def merge(cfg):
        try:
            both_have_read.wait()
        except threading.BrokenBarrierError:
            pass
        cfg["value_merges"] = {"q2": [["Group", "a", "b"]]}
        return cfg

    def edit(mutate):
        repo.update_material_config(auth, cust, case, mat, mutate)

    threads = [threading.Thread(target=edit, args=(m,)) for m in (rename, merge)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    assert not any(t.is_alive() for t in threads), "an editor never finished"

    cfg = repo.load_material_config(auth, cust, case, mat)
    assert cfg.get("question_labels") == {"q1": "Renamed"}
    assert cfg.get("value_merges") == {"q2": [["Group", "a", "b"]]}


def test_many_marks_at_once_all_survive(material):
    """The narrower version: one key, appended to from several places."""
    repo, auth, cust, case, mat = material
    ready = threading.Barrier(8)

    def mark(name: str):
        def mutate(cfg):
            cfg.setdefault("marked_classifiers", []).append(name)
            return cfg
        ready.wait(timeout=5)
        repo.update_material_config(auth, cust, case, mat, mutate)

    threads = [threading.Thread(target=mark, args=(f"var{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    marked = repo.load_material_config(auth, cust, case, mat)["marked_classifiers"]
    assert sorted(marked) == [f"var{i}" for i in range(8)]


def test_a_mutation_that_returns_nothing_still_saves(material):
    """Changing the dict in place is the obvious way to write one of these."""
    repo, auth, cust, case, mat = material

    def in_place(cfg):
        cfg["question_labels"] = {"q1": "Set in place"}

    repo.update_material_config(auth, cust, case, mat, in_place)
    assert repo.load_material_config(auth, cust, case, mat)["question_labels"] == {
        "q1": "Set in place"}
