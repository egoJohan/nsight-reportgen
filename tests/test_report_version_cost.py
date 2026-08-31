"""Reading one report's version must cost one sidecar read, not a case listing.

`report_version` fills the ETag on every report GET. It was implemented by
listing the whole case and picking the matching ref out of the result, so
opening ONE report read the sidecar of EVERY report in the case and discarded
all but one — 56 hive reads of 28 sidecars, twice over, on a hive that serves
requests one at a time. The cost grew with the number of reports in the case,
which is the wrong direction for a case that accumulates work.
"""
from reportbuilder.store.repository_client import RepositoryClient


class _Repo:
    """Records which repository call the client reaches for."""

    LOCK_RENEW_SECONDS = 30

    def __init__(self):
        self.calls: list[str] = []

    def list_reports(self, *a, **k):
        self.calls.append("list_reports")
        raise AssertionError("report_version must not list the whole case")

    def report_version(self, auth, customer_id, case_id, report_id):
        self.calls.append("report_version")
        return 7


class _Case:
    id = "case-1"
    customer_id = "cust-1"


def _client(repo):
    c = RepositoryClient.__new__(RepositoryClient)
    c.repo = repo
    c.auth = object()
    c.user = None
    c._case = lambda case_id: _Case()
    return c


def test_report_version_asks_for_one_report_not_a_listing():
    repo = _Repo()
    assert _client(repo).report_version("case-1", "rep-1") == 7
    assert repo.calls == ["report_version"]


def test_a_missing_sidecar_reads_as_version_zero():
    """An unknown report is 'no version I know of', not an error: the ETag path
    must not fail a GET because a sidecar has not been written yet."""
    class Missing(_Repo):
        def report_version(self, auth, customer_id, case_id, report_id):
            self.calls.append("report_version")
            return 0

    assert _client(Missing()).report_version("case-1", "nope") == 0
