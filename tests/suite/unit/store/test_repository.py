"""Asiakas -> Case -> Raportti (Trello: Asiakkuuden hallinta).

Uses the in-memory seam, which mirrors datahive's awkward behaviours (NotFound
for forbidden, consent on delete, path caveats) so these tests fail here rather
than in production.
"""
import json

import pytest

from reportbuilder.store import paths as P
from reportbuilder.store.memory_objects import InMemoryObjectStore
from reportbuilder.store.repository import Repository
from reportbuilder.store.seam import AuthContext, NotFound


@pytest.fixture
def store():
    return InMemoryObjectStore()


@pytest.fixture
def repo(store):
    return Repository(store)


@pytest.fixture
def auth():
    return AuthContext(token="user-1")


class TestHierarchy:
    def test_a_case_belongs_to_exactly_one_customer(self, repo, auth):
        a = repo.create_customer(auth, "Acme")
        b = repo.create_customer(auth, "Beta")
        case = repo.create_case(auth, a.id, "Brändi")
        assert [c.id for c in repo.list_cases(auth, a.id)] == [case.id]
        assert repo.list_cases(auth, b.id) == []

    def test_a_report_belongs_to_exactly_one_case(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k1 = repo.create_case(auth, c.id, "Case 1")
        k2 = repo.create_case(auth, c.id, "Case 2")
        repo.save_report(auth, c.id, k1.id, json.dumps({"name": "R"}))
        assert len(repo.list_reports(auth, c.id, k1.id)) == 1
        assert repo.list_reports(auth, c.id, k2.id) == []

    def test_creating_a_case_under_an_unknown_customer_fails(self, repo, auth):
        with pytest.raises(NotFound):
            repo.create_case(auth, "cust-nope", "Case")


class TestNaming:
    def test_report_default_name_is_one_based_and_counts_up(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Case")
        assert repo.next_report_name(auth, c.id, k.id) == "Raportti 1"
        repo.save_report(auth, c.id, k.id, json.dumps({"name": "Raportti 1"}))
        assert repo.next_report_name(auth, c.id, k.id) == "Raportti 2"

    def test_rename_is_metadata_only_and_moves_no_data(self, repo, store, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Old")
        repo.save_report(auth, c.id, k.id, json.dumps({"name": "R"}))
        before = set(store.objects)

        repo.rename_customer(auth, c.id, "Acme Oy")
        repo.rename_case(auth, c.id, k.id, "New")

        assert set(store.objects) == before, "a rename must not move any object"
        assert repo.get_customer(auth, c.id).name == "Acme Oy"
        assert repo.get_case(auth, c.id, k.id).name == "New"


class TestReports:
    def test_report_json_round_trips_verbatim(self, repo, auth):
        """The serde invariant: byte-for-byte, key order included."""
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Case")
        raw = '{"z":1,"a":{"n":[1.0,2.5]},"name":"Raportti 1","m":"ää€"}'
        r = repo.save_report(auth, c.id, k.id, raw)
        assert repo.load_report(auth, c.id, k.id, r.id) == raw

    def test_saving_with_an_id_replaces_in_place(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Case")
        r = repo.save_report(auth, c.id, k.id, json.dumps({"name": "v1"}))
        repo.save_report(auth, c.id, k.id, json.dumps({"name": "v2"}), report_id=r.id)
        assert len(repo.list_reports(auth, c.id, k.id)) == 1
        assert json.loads(repo.load_report(auth, c.id, k.id, r.id))["name"] == "v2"

    def test_duplicate_copies_every_setting_under_a_new_id(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Case")
        src = repo.save_report(auth, c.id, k.id,
                               json.dumps({"name": "Alkuperäinen", "charts": [1, 2, 3]}))
        dup = repo.duplicate_report(auth, c.id, k.id, src.id, "Kopio")
        assert dup.id != src.id
        copied = json.loads(repo.load_report(auth, c.id, k.id, dup.id))
        assert copied["charts"] == [1, 2, 3] and copied["name"] == "Kopio"
        # the source is untouched
        assert json.loads(repo.load_report(auth, c.id, k.id, src.id))["name"] == "Alkuperäinen"


class TestPermissionScoping:
    """The seam enforces path caveats, so the repository inherits them. These
    assert the grant shapes Speksi 2 names (P-O-05, P-O-06/07)."""

    def test_a_customer_grant_sees_that_customer_only(self, repo, store, auth):
        a = repo.create_customer(auth, "Acme")
        b = repo.create_customer(auth, "Beta")
        repo.create_case(auth, a.id, "A-case")
        repo.create_case(auth, b.id, "B-case")

        scoped = AuthContext(token="only-acme")
        store.caveats["only-acme"] = [P.customer_prefix(a.id)]
        assert [c.id for c in repo.list_customers(scoped)] == [a.id]
        assert len(repo.list_cases(scoped, a.id)) == 1
        assert repo.list_cases(scoped, b.id) == []

    def test_a_single_case_grant_sees_its_customer_but_not_sibling_cases(
            self, repo, store, auth):
        # P-O-06/07: access to one case WITHOUT access to the whole customer.
        c = repo.create_customer(auth, "Acme")
        k1 = repo.create_case(auth, c.id, "Mine")
        repo.create_case(auth, c.id, "Not mine")

        scoped = AuthContext(token="one-case")
        store.caveats["one-case"] = [P.case_prefix(c.id, k1.id),
                                     P.customer_meta_path(c.id)]
        assert [x.id for x in repo.list_cases(scoped, c.id)] == [k1.id]
        # the customer is still nameable, or the UI could not label the case
        assert repo.get_customer(scoped, c.id).name == "Acme"

    def test_an_out_of_scope_report_is_not_found_not_forbidden(self, repo, store, auth):
        a = repo.create_customer(auth, "Acme")
        b = repo.create_customer(auth, "Beta")
        kb = repo.create_case(auth, b.id, "Beta case")
        r = repo.save_report(auth, b.id, kb.id, json.dumps({"name": "secret"}))

        scoped = AuthContext(token="only-acme")
        store.caveats["only-acme"] = [P.customer_prefix(a.id)]
        with pytest.raises(NotFound):
            repo.load_report(scoped, b.id, kb.id, r.id)
