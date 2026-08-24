"""One person edits a report at a time.

Saving a report is a whole-document replace, so two editors do not merely
conflict — the second one's save erases everything the first did, including
slides they never touched, and nobody is told. Demonstrated against the running
app before this existed: two users edited DIFFERENT slides, both got 200, and
one edit was gone.

The lock makes that impossible. What it must never do is strand a report:
somebody's browser will crash with the lock held, and no unload handler runs
when a laptop closes.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext


@pytest.fixture
def auth():
    return AuthContext(token="t")


@pytest.fixture
def repo():
    return Repository(InMemoryObjectStore())


@pytest.fixture
def report(repo, auth):
    """A customer, a case and a report to lock."""
    c = repo.create_customer(auth, "Asiakas")
    k = repo.create_case(auth, c.id, "Tutkimus")
    r = repo.save_report(auth, c.id, k.id, '{"name":"R","charts":[]}')
    return c.id, k.id, r.id


def test_the_first_person_gets_the_lock(repo, auth, report):
    cust, case, rid = report
    mine, lock = repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    assert mine is True
    assert lock["user_name"] == "Johan"


def test_a_second_person_is_refused_and_told_who_has_it(repo, auth, report):
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    mine, held = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is False
    # Refusing without saying who would leave the second person with nothing to
    # do but guess or wait.
    assert held["user_name"] == "Johan"


def test_the_same_person_is_never_locked_out_of_their_own_work(repo, auth, report):
    """A second tab, a refresh, a reconnect, another device — same human."""
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    mine, _ = repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    assert mine is True


def test_renewing_keeps_the_original_acquired_time(repo, auth, report):
    cust, case, rid = report
    _, first = repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    _, again = repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    # "Locked by Johan since 14:03" should say when he started, not when his
    # browser last checked in.
    assert again["acquired_at"] == first["acquired_at"]


def test_a_lock_nobody_renews_expires(repo, auth, report):
    """THE property. A crashed browser must not strand a report."""
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    _age_the_lock(repo, auth, cust, case, rid, seconds=Repository.LOCK_TTL_SECONDS + 5)

    assert repo._lock_state(auth, cust, case, rid) is None
    mine, _ = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is True


def test_a_lock_renewed_recently_does_not_expire(repo, auth, report):
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    _age_the_lock(repo, auth, cust, case, rid, seconds=Repository.LOCK_TTL_SECONDS - 20)
    mine, _ = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is False


def test_a_lock_with_an_unreadable_timestamp_is_treated_as_dead(repo, auth, report):
    """A timestamp nobody can parse is not evidence that anyone is still there."""
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    path = P.report_lock_path(cust, case, rid)
    d = repo._read_json(auth, path)
    d["renewed_at"] = "not a timestamp"
    d["tabs"] = {tab: "not a timestamp" for tab in (d.get("tabs") or {"_": ""})}
    repo._write_json(auth, path, d, [P.LABEL_REPORT_LOCK])
    assert repo._lock_state(auth, cust, case, rid) is None


def test_the_holder_can_release_it(repo, auth, report):
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    assert repo.unlock_report(auth, cust, case, rid, "u1") is True
    mine, _ = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is True


def test_nobody_else_can_release_it(repo, auth, report):
    """A lock anyone may drop is not a lock. An abandoned one expires; it is not
    for other people to tidy away."""
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    assert repo.unlock_report(auth, cust, case, rid, "u2") is False
    mine, _ = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is False


def test_releasing_a_report_nobody_locked_is_not_an_error(repo, auth, report):
    """Closing an editor that never took the lock is ordinary, not exceptional."""
    cust, case, rid = report
    assert repo.unlock_report(auth, cust, case, rid, "u1") is True


def test_the_case_lists_its_live_locks(repo, auth, report):
    cust, case, rid = report
    other = repo.save_report(auth, cust, case, '{"name":"R2","charts":[]}')
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")

    locks = repo.report_locks(auth, cust, case)
    assert set(locks) == {rid}
    assert locks[rid]["user_name"] == "Johan"
    assert other.id not in locks


def test_expired_locks_are_left_out_of_the_listing(repo, auth, report):
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    _age_the_lock(repo, auth, cust, case, rid, seconds=Repository.LOCK_TTL_SECONDS + 5)
    assert repo.report_locks(auth, cust, case) == {}


def test_saving_records_who_saved_it(repo, auth, report):
    cust, case, rid = report
    repo.save_report(auth, cust, case, '{"name":"R","charts":[]}',
                     report_id=rid, modified_by="Johan")
    ref = next(r for r in repo.list_reports(auth, cust, case) if r.id == rid)
    # This is what the case page shows instead of counting charts, and it costs
    # nothing: the listing already reads this sidecar.
    assert ref.modified_by == "Johan"
    assert ref.modified_at


def _age_the_lock(repo, auth, cust, case, rid, *, seconds: float) -> None:
    """Backdate the lock, as an editor that stopped checking in would.

    Both the lock's own renewal AND every tab's, because a lock is kept alive by
    its open editors: ageing only the outer timestamp would leave the tabs
    looking fresh, which is not a state any real editor produces.
    """
    path = P.report_lock_path(cust, case, rid)
    d = repo._read_json(auth, path)
    stale = (datetime.now(timezone.utc)
             - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    d["renewed_at"] = stale
    d["tabs"] = {tab: stale for tab in (d.get("tabs") or {"_": stale})}
    repo._write_json(auth, path, d, [P.LABEL_REPORT_LOCK])


def test_signing_out_hands_back_every_lock_that_person_holds(repo, auth, report):
    """Signing out is a deliberate "I am finished".

    Waiting out the expiry would bar the report for two minutes for no reason,
    and the person signing out at the end of the day is exactly the one whose
    colleague wants the report next.
    """
    cust, case, rid = report
    other = repo.save_report(auth, cust, case, '{"name":"R2","charts":[]}')
    repo.lock_report(auth, cust, case, rid, "u1", "Johan")
    repo.lock_report(auth, cust, case, other.id, "u1", "Johan")
    # Somebody else's lock must survive it.
    third = repo.save_report(auth, cust, case, '{"name":"R3","charts":[]}')
    repo.lock_report(auth, cust, case, third.id, "u2", "Maija")

    assert repo.release_user_locks(auth, "u1") == 2
    locks = repo.report_locks(auth, cust, case)
    assert set(locks) == {third.id}
    assert locks[third.id]["user_name"] == "Maija"


def test_signing_out_with_nothing_open_is_harmless(repo, auth):
    assert repo.release_user_locks(auth, "nobody") == 0


def test_closing_one_tab_does_not_take_the_report_from_your_other_tab(repo, auth, report):
    """The self-inflicted lockout, and the one failure this must not have.

    Two tabs, one person. Closing one released the lock outright — the other tab
    got the report back only because it re-acquired on its next renewal, and in
    the thirty seconds between, anybody could have taken it. With unsaved work
    on screen in the tab that never left.
    """
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan", tab_id="tab-a")
    repo.lock_report(auth, cust, case, rid, "u1", "Johan", tab_id="tab-b")

    # Tab B closes.
    assert repo.unlock_report(auth, cust, case, rid, "u1", tab_id="tab-b") is False
    # Tab A is still editing, so the report is still hers.
    held = repo._lock_state(auth, cust, case, rid)
    assert held is not None
    assert set(held["tabs"]) == {"tab-a"}
    mine, _ = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is False


def test_closing_the_last_tab_does_release_it(repo, auth, report):
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan", tab_id="tab-a")
    repo.lock_report(auth, cust, case, rid, "u1", "Johan", tab_id="tab-b")
    repo.unlock_report(auth, cust, case, rid, "u1", tab_id="tab-b")
    assert repo.unlock_report(auth, cust, case, rid, "u1", tab_id="tab-a") is True
    mine, _ = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is True


def test_a_tab_that_stops_checking_in_stops_holding_it(repo, auth, report):
    """A crashed tab must not keep the report for the tab that is still alive
    forever — nor take it from it. Each editor stands on its own."""
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan", tab_id="tab-a")
    repo.lock_report(auth, cust, case, rid, "u1", "Johan", tab_id="tab-b")
    # Tab B's machine sleeps; tab A keeps working.
    path = P.report_lock_path(cust, case, rid)
    d = repo._read_json(auth, path)
    d["tabs"]["tab-b"] = (datetime.now(timezone.utc)
                          - timedelta(seconds=Repository.LOCK_TTL_SECONDS + 5)
                          ).isoformat(timespec="seconds")
    repo._write_json(auth, path, d, [P.LABEL_REPORT_LOCK])

    held = repo._lock_state(auth, cust, case, rid)
    assert set(held["tabs"]) == {"tab-a"}


def test_a_locked_report_cannot_be_deleted_by_someone_else(repo, auth, report):
    """Not a lost edit — a lost report.

    Only the save was guarded at first, which left the more destructive paths
    open: while somebody had a report open and was working in it, anybody else
    could delete it out from under them.
    """
    from reportbuilder.api.routes_reports import _refuse_if_locked_elsewhere
    from fastapi import HTTPException
    from reportbuilder.auth.permissions import User

    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan", tab_id="a")

    class _Client:
        def report_lock(self, case_id, report_id):
            return repo._lock_state(auth, cust, case, report_id)

    other = User(id="u2", email="m@example.com", name="Maija")
    with pytest.raises(HTTPException) as caught:
        _refuse_if_locked_elsewhere(_Client(), case, rid, other, "deleted")
    assert caught.value.status_code == 409
    assert "Johan" in caught.value.detail

    # The holder is not blocked from their own report.
    holder = User(id="u1", email="j@example.com", name="Johan")
    _refuse_if_locked_elsewhere(_Client(), case, rid, holder, "deleted")


def test_a_store_that_cannot_answer_does_not_block_the_delete(repo, auth, report):
    """A legacy client or a test double reports no locks rather than making the
    study undeletable — the guard must fail open, not brick the app."""
    from reportbuilder.api.routes_cases import _locks

    class _Mute:
        pass

    class _Broken:
        def report_locks(self, case_id):
            raise RuntimeError("no such thing here")

    _cust, case, _rid = report
    assert _locks(_Mute(), case) == {}
    assert _locks(_Broken(), case) == {}
    # The guard itself is exercised through the ROUTE, in
    # tests/suite/integration/api/test_case_delete_lock.py — this file only
    # covers the fallback, because a test that re-implements the guard's own
    # filtering and asserts on that passes with the guard deleted outright.


# ---------------------------------------------------------------------------
# Signing out on one device.
#
# A person on a laptop and a phone is one user id. Releasing every lock they
# hold meant signing out on the phone dropped the lock under the report being
# typed into on the laptop. That tab took it back on its next renewal thirty
# seconds later — leaving thirty seconds in which anybody could have taken the
# report from someone who never left, with unsaved work on their screen.
# ---------------------------------------------------------------------------

def test_signing_out_on_one_device_leaves_the_other_one_editing(repo, auth, report):
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan",
                     tab_id="laptop", session_id="session-laptop")
    repo.lock_report(auth, cust, case, rid, "u1", "Johan",
                     tab_id="phone", session_id="session-phone")

    assert repo.release_user_locks(auth, "u1", session_id="session-phone") == 1

    held = repo._lock_state(auth, cust, case, rid)
    assert held is not None, "the laptop was still editing"
    assert set(held["tabs"]) == {"laptop"}
    mine, _ = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is False


def test_signing_out_of_the_only_session_still_hands_the_report_back(repo, auth,
                                                                    report):
    """The behaviour that made the blanket release worth having in the first
    place: the person who signs out at the end of the day is exactly the one
    whose colleague wants the report next."""
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan",
                     tab_id="a", session_id="session-a")
    assert repo.release_user_locks(auth, "u1", session_id="session-a") == 1
    mine, _ = repo.lock_report(auth, cust, case, rid, "u2", "Maija")
    assert mine is True


def test_a_lock_taken_before_sessions_were_recorded_is_left_alone(repo, auth, report):
    """An editor that never said which sign-in it belongs to is not guessed at.
    Dropping it would be the very failure this prevents."""
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan", tab_id="old")

    assert repo.release_user_locks(auth, "u1", session_id="session-new") == 0
    assert repo._lock_state(auth, cust, case, rid) is not None


def test_without_a_session_every_lock_still_goes(repo, auth, report):
    """Deleting or demoting a user: there is no session left to speak for
    them, so everything they hold is handed back."""
    cust, case, rid = report
    repo.lock_report(auth, cust, case, rid, "u1", "Johan",
                     tab_id="a", session_id="session-a")
    repo.lock_report(auth, cust, case, rid, "u1", "Johan",
                     tab_id="b", session_id="session-b")
    assert repo.release_user_locks(auth, "u1") == 1
    assert repo._lock_state(auth, cust, case, rid) is None
