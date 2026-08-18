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
from reportbuilder.store.seam import AuthContext, ConsentRequired, NotFound


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


class TestRecentReports:
    """Front page: the caller's 10 most recently modified reports, newest first.

    Modification time is nSight's own record — datahive exposes none (no field
    in the listing, no Last-Modified on the GET, verified 2026-08-18).
    """

    def _report(self, repo, auth, cust, case, name, when):
        r = repo.save_report(auth, cust, case, json.dumps({"name": name}))
        # Rewrite the sidecar's timestamp so ordering is deterministic rather
        # than dependent on how fast the test machine runs.
        meta = P.report_meta_path(cust, case, r.id)
        d = json.loads(repo.store.get(auth, meta).decode())
        d["modified_at"] = when
        repo.store.put(auth, meta, json.dumps(d).encode(), "application/json",
                       labels=[P.LABEL_REPORT_META])
        return r

    def test_newest_first_across_every_customer(self, repo, auth):
        a = repo.create_customer(auth, "Acme")
        b = repo.create_customer(auth, "Beta")
        ka = repo.create_case(auth, a.id, "A")
        kb = repo.create_case(auth, b.id, "B")
        self._report(repo, auth, a.id, ka.id, "vanhin", "2026-01-01T00:00:00+00:00")
        self._report(repo, auth, b.id, kb.id, "uusin", "2026-08-18T00:00:00+00:00")
        self._report(repo, auth, a.id, ka.id, "keskimm", "2026-05-05T00:00:00+00:00")

        assert [r.name for r in repo.recent_reports(auth)] == ["uusin", "keskimm", "vanhin"]

    def test_limited_to_ten_by_default(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Case")
        for i in range(14):
            self._report(repo, auth, c.id, k.id, f"R{i:02d}",
                         f"2026-08-{i + 1:02d}T00:00:00+00:00")
        recents = repo.recent_reports(auth)
        assert len(recents) == 10
        assert recents[0].name == "R13"  # newest kept, oldest dropped

    def test_only_reports_the_caller_may_see(self, repo, store, auth):
        a = repo.create_customer(auth, "Acme")
        b = repo.create_customer(auth, "Beta")
        ka = repo.create_case(auth, a.id, "A")
        kb = repo.create_case(auth, b.id, "B")
        self._report(repo, auth, a.id, ka.id, "mine", "2026-01-01T00:00:00+00:00")
        self._report(repo, auth, b.id, kb.id, "theirs", "2026-08-18T00:00:00+00:00")

        scoped = AuthContext(token="only-acme")
        store.caveats["only-acme"] = [P.customer_prefix(a.id)]
        # "theirs" is newer, so it would lead the list if scoping were ignored.
        assert [r.name for r in repo.recent_reports(scoped)] == ["mine"]

    def test_a_listed_report_that_vanishes_is_skipped_not_fatal(self, repo, store, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Case")
        r = self._report(repo, auth, c.id, k.id, "doomed", "2026-08-01T00:00:00+00:00")
        self._report(repo, auth, c.id, k.id, "kept", "2026-08-02T00:00:00+00:00")
        # Another session deletes it between our listing and our read.
        del store.objects[P.report_meta_path(c.id, k.id, r.id)]
        assert [x.name for x in repo.recent_reports(auth)] == ["kept"]


class TestReportListingUsesSidecars:
    def test_listing_a_case_never_reads_a_report_body(self, repo, store, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Case")
        repo.save_report(auth, c.id, k.id, json.dumps({"name": "Iso raportti"}))

        body = P.report_path(c.id, k.id, repo.list_reports(auth, c.id, k.id)[0].id)
        reads: list[str] = []
        original = store.get
        store.get = lambda a, p: (reads.append(p), original(a, p))[1]
        try:
            names = [r.name for r in repo.list_reports(auth, c.id, k.id)]
        finally:
            store.get = original

        assert names == ["Iso raportti"]
        assert body not in reads, "listing must not fetch the report body"


class TestFindCase:
    """The URL surface is still case-rooted, so the app often holds only a case
    id and must resolve the rest."""

    def test_finds_a_case_and_its_customer(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Testcase 1")
        found = repo.find_case(auth, k.id)
        assert found is not None
        assert found.name == "Testcase 1" and found.customer_id == c.id

    def test_unknown_case_returns_none(self, repo, auth):
        assert repo.find_case(auth, "case-nope") is None

    def test_a_case_outside_the_caller_scope_is_indistinguishable_from_absent(
            self, repo, store, auth):
        a = repo.create_customer(auth, "Acme")
        b = repo.create_customer(auth, "Beta")
        hidden = repo.create_case(auth, b.id, "Not yours")
        scoped = AuthContext(token="only-acme")
        store.caveats["only-acme"] = [P.customer_prefix(a.id)]
        assert repo.find_case(scoped, hidden.id) is None

    def test_does_not_confuse_a_case_id_appearing_elsewhere_in_a_path(self, repo, auth):
        # The case id is matched at its own path position, not by substring:
        # a customer id that happens to contain it must not match.
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "Real")
        assert repo.find_case(auth, c.id) is None  # a customer id is not a case id
        assert repo.find_case(auth, k.id).name == "Real"


class TestMaterials:
    """Aineisto: the .sav a tutkimus is built from, plus its curation sidecar."""

    SAV = bytes([0, 255, 26]) + b"\r\n$FL2@(#) SPSS DATA FILE\x00" + bytes(range(256))

    def test_bytes_round_trip_exactly(self, repo, auth):
        # nSight re-parses the .sav on every open, so one altered byte is a
        # corrupted dataset.
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "T1")
        m = repo.attach_material(auth, c.id, k.id, "survey.sav", self.SAV)
        assert repo.get_material(auth, c.id, k.id, m.id) == self.SAV

    def test_listing_reads_sidecars_not_sav_bodies(self, repo, store, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "T1")
        m = repo.attach_material(auth, c.id, k.id, "iso.sav", self.SAV)
        body = P.material_path(c.id, k.id, m.id)

        reads: list[str] = []
        original = store.get
        store.get = lambda a, p: (reads.append(p), original(a, p))[1]
        try:
            names = [x.name for x in repo.list_materials(auth, c.id, k.id)]
        finally:
            store.get = original

        assert names == ["iso.sav"]
        assert body not in reads, "a listing must not pull the .sav body"

    def test_config_starts_empty_and_survives_a_round_trip(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "T1")
        m = repo.attach_material(auth, c.id, k.id, "s.sav", self.SAV)
        # A freshly uploaded material has no curation; that is not an error.
        assert repo.load_material_config(auth, c.id, k.id, m.id) == {}

        curation = {"groups": [{"name": "Battery", "members": ["q1", "q2"]}],
                    "word_merges": {"esper": "esperi"}}
        repo.save_material_config(auth, c.id, k.id, m.id, curation)
        assert repo.load_material_config(auth, c.id, k.id, m.id) == curation

    def test_saving_config_does_not_orphan_the_sav(self, repo, auth):
        # The sidecar carries the material's identity as well as its curation;
        # a blind overwrite would leave the .sav unreachable.
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "T1")
        m = repo.attach_material(auth, c.id, k.id, "nimetty.sav", self.SAV)
        repo.save_material_config(auth, c.id, k.id, m.id, {"groups": []})
        [listed] = repo.list_materials(auth, c.id, k.id)
        assert listed.name == "nimetty.sav" and listed.id == m.id

    def test_materials_do_not_leak_between_tutkimukset(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k1 = repo.create_case(auth, c.id, "T1")
        k2 = repo.create_case(auth, c.id, "T2")
        repo.attach_material(auth, c.id, k1.id, "a.sav", self.SAV)
        assert len(repo.list_materials(auth, c.id, k1.id)) == 1
        assert repo.list_materials(auth, c.id, k2.id) == []

    def test_a_scoped_caller_cannot_read_another_customer_material(
            self, repo, store, auth):
        a = repo.create_customer(auth, "Acme")
        b = repo.create_customer(auth, "Beta")
        kb = repo.create_case(auth, b.id, "Beta T")
        m = repo.attach_material(auth, b.id, kb.id, "salainen.sav", self.SAV)

        scoped = AuthContext(token="only-acme")
        store.caveats["only-acme"] = [P.customer_prefix(a.id)]
        with pytest.raises(NotFound):
            repo.get_material(scoped, b.id, kb.id, m.id)


class TestRenderCache:
    """A rendered deck stored in datahive, keyed by everything it derives from.

    Stored because rendering is expensive (LibreOffice per PDF) and the temp dir
    dies with the process — staging loses every deck on deploy. Keyed because a
    deck that silently disagrees with its data is worse than no deck.
    """

    def _setup(self, repo, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "T1")
        m = repo.attach_material(auth, c.id, k.id, "s.sav", b"savbytes")
        r = repo.save_report(auth, c.id, k.id, json.dumps({"name": "R", "charts": []}))
        return c.id, k.id, m.id, r.id

    def test_a_stored_deck_is_served_when_nothing_changed(self, repo, auth):
        cid, kid, mid, rid = self._setup(repo, auth)
        key = repo.render_key(auth, cid, kid, rid, mid)
        repo.save_render(auth, cid, kid, rid, b"PPTX-v1", key)
        assert repo.load_render(auth, cid, kid, rid, key) == b"PPTX-v1"

    def test_editing_the_report_invalidates_it(self, repo, auth):
        cid, kid, mid, rid = self._setup(repo, auth)
        key = repo.render_key(auth, cid, kid, rid, mid)
        repo.save_render(auth, cid, kid, rid, b"PPTX-v1", key)

        repo.save_report(auth, cid, kid, json.dumps({"name": "R", "charts": [1]}),
                         report_id=rid)
        assert repo.load_render(auth, cid, kid, rid,
                                repo.render_key(auth, cid, kid, rid, mid)) is None

    def test_editing_the_material_curation_invalidates_it(self, repo, auth):
        """The one a report-only key would miss: word merges and label overrides
        change the charts without touching the report definition."""
        cid, kid, mid, rid = self._setup(repo, auth)
        key = repo.render_key(auth, cid, kid, rid, mid)
        repo.save_render(auth, cid, kid, rid, b"PPTX-v1", key)

        repo.save_material_config(auth, cid, kid, mid, {"word_merges": {"esper": "esperi"}})
        assert repo.load_render(auth, cid, kid, rid,
                                repo.render_key(auth, cid, kid, rid, mid)) is None

    def test_a_never_rendered_report_is_a_miss_not_an_error(self, repo, auth):
        cid, kid, mid, rid = self._setup(repo, auth)
        assert repo.load_render(auth, cid, kid, rid,
                                repo.render_key(auth, cid, kid, rid, mid)) is None

    def test_re_rendering_replaces_the_stored_deck(self, repo, auth):
        cid, kid, mid, rid = self._setup(repo, auth)
        k1 = repo.render_key(auth, cid, kid, rid, mid)
        repo.save_render(auth, cid, kid, rid, b"PPTX-v1", k1)
        repo.save_material_config(auth, cid, kid, mid, {"x": 1})
        k2 = repo.render_key(auth, cid, kid, rid, mid)
        repo.save_render(auth, cid, kid, rid, b"PPTX-v2", k2)

        assert repo.load_render(auth, cid, kid, rid, k2) == b"PPTX-v2"
        assert repo.load_render(auth, cid, kid, rid, k1) is None

    def test_storing_a_render_keeps_the_report_name(self, repo, auth):
        # The key is stamped into the report's own sidecar, so it must not
        # clobber the name the listing reads from there.
        cid, kid, mid, rid = self._setup(repo, auth)
        repo.save_render(auth, cid, kid, rid, b"PPTX",
                         repo.render_key(auth, cid, kid, rid, mid))
        assert [r.name for r in repo.list_reports(auth, cid, kid)] == ["R"]


class TestDeletion:
    """datahive gates destructive operations behind human approval, so these
    tests drive the consent flow rather than pretending it does not exist."""

    def _approve_all(self, store, auth, fn):
        """Run *fn*, approving each consent request until it completes."""
        for _ in range(50):
            try:
                return fn()
            except ConsentRequired as exc:
                store.approve(exc.request_id)
        raise AssertionError("consent loop did not converge")

    def test_deleting_a_report_takes_its_sidecar_and_render(self, repo, store, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "T1")
        m = repo.attach_material(auth, c.id, k.id, "s.sav", b"sav")
        r = repo.save_report(auth, c.id, k.id, json.dumps({"name": "R"}))
        repo.save_render(auth, c.id, k.id, r.id, b"PPTX",
                         repo.render_key(auth, c.id, k.id, r.id, m.id))

        self._approve_all(store, auth,
                          lambda: repo.delete_report(auth, c.id, k.id, r.id))

        # A sidecar outliving its report would keep it in listings and recents.
        assert repo.list_reports(auth, c.id, k.id) == []
        assert repo.recent_reports(auth) == []

    def test_deleting_a_tutkimus_takes_its_material_and_reports(self, repo, store, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "T1")
        repo.attach_material(auth, c.id, k.id, "s.sav", b"sav")
        repo.save_report(auth, c.id, k.id, json.dumps({"name": "R"}))

        self._approve_all(store, auth, lambda: repo.delete_case(auth, c.id, k.id))

        assert repo.list_cases(auth, c.id) == []
        assert repo.list_materials(auth, c.id, k.id) == []
        assert repo.list_reports(auth, c.id, k.id) == []

    def test_deleting_a_customer_takes_every_tutkimus(self, repo, store, auth):
        c = repo.create_customer(auth, "Acme")
        keep = repo.create_customer(auth, "Beta")
        repo.create_case(auth, c.id, "T1")
        repo.create_case(auth, c.id, "T2")
        kb = repo.create_case(auth, keep.id, "Beta T")

        self._approve_all(store, auth, lambda: repo.delete_customer(auth, c.id))

        assert [x.id for x in repo.list_customers(auth)] == [keep.id]
        assert [x.id for x in repo.list_cases(auth, keep.id)] == [kb.id]

    def test_delete_demands_consent_before_it_removes_anything(self, repo, store, auth):
        c = repo.create_customer(auth, "Acme")
        k = repo.create_case(auth, c.id, "T1")
        r = repo.save_report(auth, c.id, k.id, json.dumps({"name": "R"}))

        with pytest.raises(ConsentRequired):
            repo.delete_report(auth, c.id, k.id, r.id)
        # Nothing went before approval — the gate is real, not advisory.
        assert [x.id for x in repo.list_reports(auth, c.id, k.id)] == [r.id]


class TestTemplateResolution:
    """Presentaatiopohjat: a template can be set per asiakas, per tutkimus and
    per report, the lower always winning — and an already-delivered report must
    not restyle itself when someone changes the level above it."""

    def _tree(self, repo, auth):
        c = repo.create_customer(auth, "Attendo")
        k = repo.create_case(auth, c.id, "Brändi")
        r = repo.save_report(auth, c.id, k.id,
                             json.dumps({"name": "R", "template_ref": ""}))
        return c.id, k.id, r.id

    def test_with_nothing_set_the_house_default_is_used(self, repo, auth):
        cid, kid, rid = self._tree(repo, auth)
        assert repo.resolve_template(auth, cid, kid, rid) == ("", "default")

    def test_a_customer_template_reaches_its_reports(self, repo, auth):
        cid, kid, rid = self._tree(repo, auth)
        repo.set_template(auth, "tpl-attendo", customer_id=cid)
        assert repo.resolve_template(auth, cid, kid, rid) == ("tpl-attendo", "customer")

    def test_a_tutkimus_template_overrides_its_customer(self, repo, auth):
        cid, kid, rid = self._tree(repo, auth)
        repo.set_template(auth, "tpl-customer", customer_id=cid)
        repo.set_template(auth, "tpl-case", customer_id=cid, case_id=kid)
        assert repo.resolve_template(auth, cid, kid, rid) == ("tpl-case", "case")

    def test_a_report_template_overrides_everything(self, repo, auth):
        cid, kid, rid = self._tree(repo, auth)
        repo.set_template(auth, "tpl-customer", customer_id=cid)
        repo.set_template(auth, "tpl-case", customer_id=cid, case_id=kid)
        repo.save_report(auth, cid, kid,
                         json.dumps({"name": "R", "template_ref": "tpl-report"}),
                         report_id=rid)
        assert repo.resolve_template(auth, cid, kid, rid) == ("tpl-report", "report")

    def test_clearing_a_binding_falls_back_up_the_chain(self, repo, auth):
        cid, kid, rid = self._tree(repo, auth)
        repo.set_template(auth, "tpl-customer", customer_id=cid)
        repo.set_template(auth, "tpl-case", customer_id=cid, case_id=kid)
        repo.set_template(auth, None, customer_id=cid, case_id=kid)
        assert repo.resolve_template(auth, cid, kid, rid) == ("tpl-customer", "customer")


class TestTemplatePinning:
    """"Jo luotujen raporttien pohja ei muutoksessa automaattisesti päivity,
    vaan päivitys pitää erikseen pyytää." A report already delivered to a client
    must look the same tomorrow."""

    def _rendered(self, repo, auth):
        c = repo.create_customer(auth, "Attendo")
        k = repo.create_case(auth, c.id, "Brändi")
        r = repo.save_report(auth, c.id, k.id,
                             json.dumps({"name": "R", "template_ref": ""}))
        repo.set_template(auth, "tpl-v1", customer_id=c.id)
        repo.pin_template(auth, c.id, k.id, r.id, "tpl-v1")
        return c.id, k.id, r.id

    def test_changing_the_customer_template_leaves_a_delivered_report_alone(
            self, repo, auth):
        cid, kid, rid = self._rendered(repo, auth)
        repo.set_template(auth, "tpl-v2", customer_id=cid)
        assert repo.resolve_template(auth, cid, kid, rid) == ("tpl-v1", "pinned")

    def test_a_new_report_picks_up_the_new_template(self, repo, auth):
        cid, kid, _ = self._rendered(repo, auth)
        repo.set_template(auth, "tpl-v2", customer_id=cid)
        fresh = repo.save_report(auth, cid, kid,
                                 json.dumps({"name": "New", "template_ref": ""}))
        assert repo.resolve_template(auth, cid, kid, fresh.id) == ("tpl-v2", "customer")

    def test_requesting_the_update_moves_the_report_on(self, repo, auth):
        cid, kid, rid = self._rendered(repo, auth)
        repo.set_template(auth, "tpl-v2", customer_id=cid)
        repo.clear_pinned_template(auth, cid, kid, rid)
        assert repo.resolve_template(auth, cid, kid, rid) == ("tpl-v2", "customer")

    def test_pinning_does_not_disturb_the_report_name(self, repo, auth):
        # The pin lives in the same sidecar the listing reads its name from.
        cid, kid, rid = self._rendered(repo, auth)
        assert [r.name for r in repo.list_reports(auth, cid, kid)] == ["R"]
