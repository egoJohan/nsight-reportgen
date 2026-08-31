"""Which reports in a case are rendering — answered from memory.

The case page shows a "Generating…" badge, and kept it honest by re-fetching
the whole report list every three seconds while any render was running. That
list costs one hive read per report plus one per lock — 78 serialised
round-trips on a 28-report case — to answer a question the server already holds
in a dict. A thirty-second deck render therefore cost roughly ten polls, ~780
hive calls, from a single browser that was only watching.
"""
from reportbuilder.api import routes_render as R


def test_only_this_case_s_renders_are_returned():
    R._active_renders.clear()
    R._active_renders[("case-1", "rep-a")] = object()
    R._active_renders[("case-1", "rep-b")] = object()
    R._active_renders[("case-2", "rep-c")] = object()
    try:
        assert R.active_renders_for_case("case-1") == ["rep-a", "rep-b"]
        assert R.active_renders_for_case("case-2") == ["rep-c"]
        assert R.active_renders_for_case("case-none") == []
    finally:
        R._active_renders.clear()


def test_it_reads_the_shared_dict_under_its_lock():
    """The rollout mutates this dict from other threads; a bare iteration can
    raise 'dictionary changed size during iteration'."""
    import inspect

    src = inspect.getsource(R.active_renders_for_case)
    assert "_active_renders_lock" in src


def test_the_answer_costs_no_storage_reads():
    """The whole point: this must not touch the hive."""
    import inspect

    src = inspect.getsource(R.active_renders_for_case)
    for forbidden in ("client.", "repo.", "store.", "list_reports"):
        assert forbidden not in src, f"{forbidden} would put this back on the hive"
