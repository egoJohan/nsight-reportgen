"""A released lock must drop out of the live-lock listing.

`report_locks` lists every object labelled as a report lock and reads each one
to see whether it is still held. That is fine while locks are rare — the code
says "normally none or one" — but a lock object is never deleted (deleting is
gated behind a consent prompt, which is absurd for handing back a lock), so one
accumulates for every report anyone has ever opened. On a case with 28 reports
that had become 70 lock objects, 0 of them live, and the case page paid 70
serialised hive reads to conclude that nobody holds anything.

Releasing already rewrites the object, so it can relabel at the same time and
leave the live listing.
"""
from reportbuilder.store import paths as P


def test_there_is_a_distinct_label_for_a_released_lock():
    assert hasattr(P, "LABEL_REPORT_LOCK_RELEASED")
    assert P.LABEL_REPORT_LOCK_RELEASED != P.LABEL_REPORT_LOCK


def test_release_writes_the_released_label(monkeypatch):
    """The write that marks a lock released must also take it out of the
    listing the case page reads."""
    from reportbuilder.store.repository import Repository

    written: list[tuple[str, dict, tuple]] = []

    class R(Repository):
        def __init__(self):
            pass

        def _lock_state(self, auth, customer_id, case_id, report_id):
            return {"user_id": "u1", "tabs": {"t1": "now"}}

        def _live_tabs(self, d):
            return {}

        def _write_json(self, auth, path, payload, labels):
            written.append((path, payload, tuple(labels)))

    R().unlock_report(None, "cust-1", "case-1", "rep-1", tab_id="t1",
                      user_id="u1")
    assert written, "release must write something"
    _path, payload, labels = written[-1]
    assert payload.get("released") is True
    assert P.LABEL_REPORT_LOCK_RELEASED in labels
    assert P.LABEL_REPORT_LOCK not in labels, (
        "a released lock that keeps the live label stays in the listing, "
        "which is the cost this removes")


def test_sign_out_release_also_leaves_the_listing():
    """Signing out releases every lock this sign-in held; those must drop out
    of the live listing for the same reason an explicit unlock does."""
    import inspect

    from reportbuilder.store.repository import Repository

    src = inspect.getsource(Repository.release_user_locks)
    # The full-release write (released: True) must carry the released label.
    full = [b for b in src.split("_write_json") if '"released": True' in b
            or "'released': True" in b]
    assert full, "no full-release write found"
    assert all("LABEL_REPORT_LOCK_RELEASED" in b for b in full), (
        "a sign-out release still writes the live label, so the lock stays "
        "in the listing the case page reads")
