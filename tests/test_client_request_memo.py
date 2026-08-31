"""One request should resolve a case once, not once per storage call.

`RepositoryClient` is built per request, and nearly every method on it starts
with `self._case(case_id)` -> `repo.find_case(...)`, which reads the case
record. A single endpoint therefore read `case.json` four to eight times, and
each of those is a serialised round-trip to a hive that handles one request at
a time. The case cannot change underneath a request that is already running,
so resolving it once is the same answer for less work.
"""
from reportbuilder.store.repository_client import RepositoryClient


class _Case:
    def __init__(self, cid):
        self.id = cid
        self.customer_id = "cust-1"


class _Repo:
    LOCK_RENEW_SECONDS = 30

    def __init__(self):
        self.finds: list[str] = []

    def find_case(self, auth, case_id, user=None):
        self.finds.append(case_id)
        return _Case(case_id)


def _client(repo):
    return RepositoryClient(repo, auth=object(), user=None)


def test_the_same_case_is_resolved_once_per_request():
    repo = _Repo()
    c = _client(repo)
    for _ in range(5):
        c._case("case-1")
    assert repo.finds == ["case-1"], repo.finds


def test_different_cases_are_each_resolved():
    repo = _Repo()
    c = _client(repo)
    c._case("case-1"); c._case("case-2"); c._case("case-1")
    assert repo.finds == ["case-1", "case-2"]


def test_a_new_request_resolves_again():
    """The memo must not outlive the request — a later request has to see a
    case that was renamed or whose access changed."""
    repo = _Repo()
    _client(repo)._case("case-1")
    _client(repo)._case("case-1")
    assert repo.finds == ["case-1", "case-1"]


def test_an_unknown_case_still_raises_every_time():
    class Missing(_Repo):
        def find_case(self, auth, case_id, user=None):
            self.finds.append(case_id)
            return None

    repo = Missing()
    c = _client(repo)
    for _ in range(2):
        try:
            c._case("nope")
        except KeyError:
            pass
    assert repo.finds == ["nope", "nope"], "a miss must not be cached as absent"
