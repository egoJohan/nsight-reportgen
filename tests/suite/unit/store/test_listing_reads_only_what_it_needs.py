"""Counting cases and naming owners without reading what they do not need.

The customers page was 43 datahive round trips. Measured against the local
hive at ~17ms a call, that is most of its 1.7s, and on staging the hive is a
separate VM.

Two of those reads were pure waste, and both are here:

* 11 of the 43 were one `case.json` per case, read only to take `len()` of the
  result. `list_cases` filters on `_admits(user, info.path)` — the PATH, never
  the body — so the count is already settled by the listing.
* 7 were `settings/user/<id>.grants`, one per tenant user. `get_user` always
  loads grants, and the page uses only a display name.

These tests count the STORE CALLS, not the wall clock: a timing test on a
shared machine proves nothing, while "did it read the object" is exactly the
property that was wrong. (Johan, 2026-09-16)
"""
from __future__ import annotations

import json

import pytest

from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext

pytestmark = pytest.mark.unit

AUTH = AuthContext(token="t")


class CountingStore(InMemoryObjectStore):
    """An object store that remembers every path it was asked to READ."""

    def __init__(self):
        super().__init__()
        self.reads: list[str] = []

    def get(self, auth, path):
        self.reads.append(path)
        return super().get(auth, path)


@pytest.fixture
def repo():
    store = CountingStore()
    r = Repository(store)
    cust = r.create_customer(AUTH, "Asiakas")
    for i in range(5):
        r.create_case(AUTH, cust.id, f"Tutkimus {i}")
    for i in range(4):
        store.put(AUTH, P.user_path(f"usr-{i}"),
                  json.dumps({"id": f"usr-{i}", "email": f"u{i}@egoiq.com",
                              "name": f"Nimi {i}"}).encode(),
                  content_type="application/json", labels=[P.LABEL_USER])
    return r, store, cust.id


# ---- counting cases --------------------------------------------------------

def test_counting_cases_agrees_with_listing_them(repo):
    r, _store, cid = repo
    assert r.count_cases(AUTH, cid) == len(r.list_cases(AUTH, cid))


def test_counting_cases_reads_no_case(repo):
    """The point of the change."""
    r, store, cid = repo
    store.reads.clear()
    r.count_cases(AUTH, cid)
    case_reads = [p for p in store.reads if p.endswith("case.json")]
    assert not case_reads, f"read {len(case_reads)} cases only to count them"


def test_counting_an_empty_customer_is_zero(repo):
    r, _store, _cid = repo
    empty = r.create_customer(AUTH, "Tyhjä")
    assert r.count_cases(AUTH, empty.id) == 0


def test_counting_honours_the_same_filter_as_listing(repo):
    """A user who may see nothing counts nothing — the count must not become a
    way to learn how many studies exist behind a customer you cannot open."""
    from reportbuilder.auth.permissions import Grant, User

    r, _store, cid = repo
    stranger = User(id="usr-x", email="x@example.com", name="X",
                    grants=(Grant(scope="cust-other", mode="view"),))
    assert r.list_cases(AUTH, cid, user=stranger) == []
    assert r.count_cases(AUTH, cid, user=stranger) == 0


# ---- naming users ----------------------------------------------------------

def test_names_match_the_full_user_records(repo):
    r, _store, _cid = repo
    full = {u.id: (u.name or u.email) for u in r.list_users(AUTH)}
    assert r.list_user_names(AUTH) == full


def test_naming_users_reads_no_grants(repo):
    r, store, _cid = repo
    store.reads.clear()
    r.list_user_names(AUTH)
    grant_reads = [p for p in store.reads if p.endswith(".grants")]
    assert not grant_reads, f"read {len(grant_reads)} grant objects for names"


def test_a_user_with_no_name_falls_back_to_the_email(repo):
    r, store, _cid = repo
    store.put(AUTH, P.user_path("usr-blank"),
              json.dumps({"id": "usr-blank", "email": "blank@egoiq.com",
                          "name": ""}).encode(),
              content_type="application/json", labels=[P.LABEL_USER])
    assert r.list_user_names(AUTH)["usr-blank"] == "blank@egoiq.com"


# ---- counting every customer's cases at once --------------------------------
#
# The customers listing (the sidebar, on every page) asked for one listing per
# customer to count its studies. One listing of every case answers all of them:
# the customer is the first segment of the path. (2026-09-17)

class ListCountingStore(CountingStore):
    def __init__(self):
        super().__init__()
        self.listings = 0

    def list(self, auth, prefix, labels=None):
        self.listings += 1
        return super().list(auth, prefix, labels=labels)


@pytest.fixture
def tenant():
    store = ListCountingStore()
    r = Repository(store)
    ids = []
    for n, cases in (("A", 3), ("B", 0), ("C", 2)):
        c = r.create_customer(AUTH, n)
        ids.append(c.id)
        for i in range(cases):
            r.create_case(AUTH, c.id, f"{n}{i}")
    return r, store, ids


def test_counting_all_customers_agrees_with_counting_each(tenant):
    r, _store, ids = tenant
    counts = r.count_cases_by_customer(AUTH)
    assert {cid: counts.get(cid, 0) for cid in ids} == {
        cid: r.count_cases(AUTH, cid) for cid in ids}


def test_counting_all_customers_is_one_listing(tenant):
    r, store, _ids = tenant
    store.listings = 0
    store.reads.clear()
    r.count_cases_by_customer(AUTH)
    assert store.listings == 1
    assert not store.reads


def test_counting_all_customers_honours_the_filter(tenant):
    from reportbuilder.auth.permissions import Grant, User
    r, _store, ids = tenant
    one = User(id="usr-y", email="y@example.com", name="Y",
               grants=(Grant(scope=ids[2], mode="view"),))
    counts = r.count_cases_by_customer(AUTH, user=one)
    assert {cid: counts.get(cid, 0) for cid in ids} == {
        cid: r.count_cases(AUTH, cid, user=one) for cid in ids}
