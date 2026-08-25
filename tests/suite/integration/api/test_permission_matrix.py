"""Can one customer's analyst reach another customer's data over HTTP?

Unit tests cover may_read. This covers the whole stack: a real app, a real
store, a user with one grant, and every shape of route the API exposes.

Uses `client_memory` (see conftest.py) rather than a separate fixture: it
already builds the app with NO injected client, so `get_client` constructs the
real `RepositoryClient` over the same object store the guards read through
`app.dependency_overrides`. A fixture that injected a standalone client (as
`client_mock`/a hand-rolled `memory_hive` would) would let routes and guards
disagree about what exists, making every assertion below meaningless.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User


@pytest.fixture
def two_customers(client_memory, synthetic_bytes):
    """Attendo and Synsam, each with a study, a report and a dataset."""
    made = {}
    for name in ("Attendo", "Synsam"):
        cid = client_memory.post("/customers", json={"name": name}).json()["id"]
        kid = client_memory.post(f"/customers/{cid}/cases",
                                 json={"name": f"{name} study"}).json()["id"]
        mid = client_memory.post(
            f"/cases/{kid}/materials",
            files={"file": ("s.sav", synthetic_bytes, "application/octet-stream")},
        ).json()["material_id"]
        rid = client_memory.post(f"/cases/{kid}/reports",
                                 json={"name": f"{name} report", "render_mode": "image",
                                       "template_ref": "", "charts": []}).json()["report_id"]
        made[name] = {"cid": cid, "kid": kid, "mid": mid, "rid": rid}
    return made


def sign_in(client, monkeypatch, email, *grants, admin=False):
    """Create a user in the store the test app is using, and become them.

    `client_memory` builds its Repository inside the fixture and injects it with
    `app.dependency_overrides` — reaching for the module-level `get_repository()`
    would create a SECOND, empty store and the user would never be found.

    Overrides `current_user` directly with the exact user just saved — NOT
    `suite._helpers.sign_in_override`, which grants every customer in the
    store; these tests exist to prove a caller with a NARROW grant sees only
    what that grant covers, so the override must carry exactly the grants
    passed in, no more. `monkeypatch` is kept in the signature for existing
    call sites; it does nothing now that there is no env var to set.
    """
    from reportbuilder.api.deps_auth import current_user
    from reportbuilder.api.deps_store import get_auth, get_repository

    overrides = client.app.dependency_overrides
    repo, auth = overrides[get_repository](), overrides[get_auth]()
    user = repo.save_user(auth, User(id="", email=email, name=email.split("@")[0],
                                     is_admin=admin,
                                     grants=tuple(Grant(s, m) for s, m in grants)))
    overrides[current_user] = lambda: user


@pytest.fixture
def as_attendo_editor(client_memory, two_customers, monkeypatch):
    """Sign the client in as someone granted Attendo, edit."""
    sign_in(client_memory, monkeypatch, "maija@egoiq.com",
            (two_customers["Attendo"]["cid"], "edit"))
    return two_customers


def test_the_granted_customer_is_reachable(client_memory, as_attendo_editor):
    a = as_attendo_editor["Attendo"]
    assert client_memory.get(f"/customers/{a['cid']}/cases").status_code == 200
    assert client_memory.get(f"/cases/{a['kid']}/reports").status_code == 200


def test_the_other_customer_is_absent_from_listings(client_memory, as_attendo_editor):
    names = [c["name"] for c in client_memory.get("/customers").json()]
    assert names == ["Attendo"]


def test_the_other_customers_case_is_not_found(client_memory, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_memory.get(f"/cases/{b['kid']}/reports").status_code == 404


def test_the_other_customers_material_is_not_found(client_memory, as_attendo_editor):
    """A material id is not authorisation (spec §5.1)."""
    b = as_attendo_editor["Synsam"]
    assert client_memory.get(f"/materials/{b['mid']}/questions").status_code == 404


def test_the_other_customers_report_cannot_be_read(client_memory, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_memory.get(f"/cases/{b['kid']}/reports/{b['rid']}").status_code == 404


def test_the_other_customers_report_cannot_be_deleted(client_memory, as_attendo_editor):
    b = as_attendo_editor["Synsam"]
    assert client_memory.delete(f"/cases/{b['kid']}/reports/{b['rid']}").status_code in (403, 404)


def test_recents_shows_only_the_granted_customer(client_memory, as_attendo_editor):
    names = [r["name"] for r in client_memory.get("/reports/recent").json()]
    assert names == ["Attendo report"]


def test_a_viewer_cannot_write(client_memory, two_customers, monkeypatch):
    sign_in(client_memory, monkeypatch, "viewer@egoiq.com",
            (two_customers["Attendo"]["cid"], "view"))
    a = two_customers["Attendo"]
    assert client_memory.get(f"/cases/{a['kid']}/reports").status_code == 200
    assert client_memory.delete(f"/cases/{a['kid']}/reports/{a['rid']}").status_code == 403


def test_the_resolution_cache_does_not_leak_between_users(client_memory, two_customers, monkeypatch):
    """Spec §5.1's cache is per-process and shared. One user resolving their own
    material must not make it resolvable for another."""
    a, b = two_customers["Attendo"], two_customers["Synsam"]
    sign_in(client_memory, monkeypatch, "s@egoiq.com", (b["cid"], "edit"))
    assert client_memory.get(f"/materials/{b['mid']}/questions").status_code == 200

    sign_in(client_memory, monkeypatch, "m@egoiq.com", (a["cid"], "edit"))
    assert client_memory.get(f"/materials/{b['mid']}/questions").status_code == 404


def test_an_admin_without_grants_sees_nothing(client_memory, two_customers, monkeypatch):
    """Administering access is not having access (spec §5)."""
    sign_in(client_memory, monkeypatch, "admin@egoiq.com", admin=True)
    assert client_memory.get("/customers").json() == []


# ---------------------------------------------------------------------------
# can_edit on /cases/{id}/resolve — the read-only web view's only way to know
# whether it is looking at an editor's or a viewer's case.
# ---------------------------------------------------------------------------


def test_resolve_case_can_edit_true_for_an_editor(client_memory, as_attendo_editor):
    a = as_attendo_editor["Attendo"]
    body = client_memory.get(f"/cases/{a['kid']}/resolve").json()
    assert body["can_edit"] is True


def test_resolve_case_can_edit_false_for_a_viewer(client_memory, two_customers, monkeypatch):
    sign_in(client_memory, monkeypatch, "viewer@egoiq.com",
            (two_customers["Attendo"]["cid"], "view"))
    a = two_customers["Attendo"]
    body = client_memory.get(f"/cases/{a['kid']}/resolve").json()
    assert body["can_edit"] is False


def test_resolve_case_can_edit_ignores_is_admin(client_memory, two_customers, monkeypatch):
    """Same rule as above, one level down: an admin with only a view grant on
    this case is still a viewer here."""
    sign_in(client_memory, monkeypatch, "admin-viewer@egoiq.com",
            (two_customers["Attendo"]["cid"], "view"), admin=True)
    a = two_customers["Attendo"]
    body = client_memory.get(f"/cases/{a['kid']}/resolve").json()
    assert body["can_edit"] is False


# ---------------------------------------------------------------------------
# can_edit on /customers and /customers/{id} — same question, one level up:
# creating a study is a write against the CUSTOMER, not any one case, so the
# "New study" affordance (page + sidebar) needs the answer at this level too.
# ---------------------------------------------------------------------------


def test_get_customer_can_edit_true_for_an_editor(client_memory, as_attendo_editor):
    a = as_attendo_editor["Attendo"]
    body = client_memory.get(f"/customers/{a['cid']}").json()
    assert body["can_edit"] is True


def test_get_customer_can_edit_false_for_a_viewer(client_memory, two_customers, monkeypatch):
    sign_in(client_memory, monkeypatch, "viewer@egoiq.com",
            (two_customers["Attendo"]["cid"], "view"))
    a = two_customers["Attendo"]
    body = client_memory.get(f"/customers/{a['cid']}").json()
    assert body["can_edit"] is False


def test_list_customers_carries_can_edit_per_row(client_memory, two_customers, monkeypatch):
    """A viewer on one customer and an editor on the other sees each row say
    so — the sidebar's per-customer "New study" link needs a per-row answer,
    not one flag for the whole page."""
    sign_in(client_memory, monkeypatch, "mixed@egoiq.com",
            (two_customers["Attendo"]["cid"], "view"),
            (two_customers["Synsam"]["cid"], "edit"))
    rows = {c["name"]: c["can_edit"] for c in client_memory.get("/customers").json()}
    assert rows == {"Attendo": False, "Synsam": True}


def test_customer_can_edit_ignores_is_admin(client_memory, two_customers, monkeypatch):
    """An admin with only a view grant is a viewer — is_admin must not leak
    into this decision (admin is the right to manage users, not data)."""
    sign_in(client_memory, monkeypatch, "admin-viewer@egoiq.com",
            (two_customers["Attendo"]["cid"], "view"), admin=True)
    a = two_customers["Attendo"]
    body = client_memory.get(f"/customers/{a['cid']}").json()
    assert body["can_edit"] is False


# ---------------------------------------------------------------------------
# Routes addressed by BOTH ids: /customers/{c}/cases/{k}/…
#
# The case id is what authorises; the customer id then ADDRESSES storage. Nobody
# checked they were the same customer, so an analyst could take a case they DO
# hold and paste any other customer's id beside it.
# ---------------------------------------------------------------------------

def test_a_foreign_customer_id_beside_your_own_case_reads_nothing(
        client_memory, as_attendo_editor):
    """It answered with Synsam's template binding — the id and its name."""
    mine, theirs = as_attendo_editor["Attendo"], as_attendo_editor["Synsam"]
    r = client_memory.get(f"/customers/{theirs['cid']}/cases/{mine['kid']}/template")
    assert r.status_code == 404, r.text


def test_the_same_holds_for_a_report_under_someone_elses_customer(
        client_memory, as_attendo_editor):
    mine, theirs = as_attendo_editor["Attendo"], as_attendo_editor["Synsam"]
    r = client_memory.get(
        f"/customers/{theirs['cid']}/cases/{mine['kid']}/reports/{mine['rid']}/template")
    assert r.status_code == 404, r.text


def test_and_nothing_can_be_written_under_a_customer_you_do_not_hold(
        client_memory, as_attendo_editor):
    """The write half, which was NOT reachable: both of these address storage by
    the customer id they were handed, and both happened to fail on the lookup
    that pairing produces. Pinned so it stays that way — the guard is now what
    stops them, rather than luck about which lookup runs first.
    """
    mine, theirs = as_attendo_editor["Attendo"], as_attendo_editor["Synsam"]
    r = client_memory.put(
        f"/customers/{theirs['cid']}/cases/{mine['kid']}/reports/{mine['rid']}/template",
        json={"template_id": ""})
    assert r.status_code == 404, r.text

    r = client_memory.put(f"/customers/{theirs['cid']}/cases/{mine['kid']}/template",
                          json={"template_id": "whatever"})
    assert r.status_code == 404, r.text


def test_your_own_pair_still_works(client_memory, as_attendo_editor):
    """The check must not cost the ordinary case anything."""
    mine = as_attendo_editor["Attendo"]
    assert client_memory.get(
        f"/customers/{mine['cid']}/cases/{mine['kid']}/template").status_code == 200
    assert client_memory.get(
        f"/customers/{mine['cid']}/cases/{mine['kid']}/materials").status_code == 200
    assert client_memory.get(
        f"/customers/{mine['cid']}/cases/{mine['kid']}").status_code == 200


def test_a_scope_listed_twice_with_different_modes_is_refused(
    client_memory, two_customers, monkeypatch
):
    """A body naming one scope as both view and edit does not know what it is
    asking for. Guessing for the caller hides the mistake inside a permission
    decision nobody looks at again.

    `_best` now resolves such a pair deterministically, so this is belt and
    braces — but the pair used to make the answer depend on which order the
    admin's client happened to send them in.
    """
    sign_in(client_memory, monkeypatch, "admin@egoiq.com", admin=True)
    cid = two_customers["Attendo"]["cid"]
    target = client_memory.get("/users").json()[0]["id"]
    r = client_memory.put(f"/users/{target}/grants", json={"grants": [
        {"scope": cid, "mode": "view"},
        {"scope": cid, "mode": "edit"},
    ]})
    assert r.status_code == 422, r.text
    assert "twice" in r.text


def test_the_same_grant_sent_twice_is_stored_once(
    client_memory, two_customers, monkeypatch
):
    """An exact duplicate is harmless to permissions but would show one grant
    as two rows on the admin screen."""
    sign_in(client_memory, monkeypatch, "admin@egoiq.com", admin=True)
    cid = two_customers["Attendo"]["cid"]
    target = client_memory.get("/users").json()[0]["id"]
    r = client_memory.put(f"/users/{target}/grants", json={"grants": [
        {"scope": cid, "mode": "edit"},
        {"scope": cid, "mode": "edit"},
    ]})
    assert r.status_code == 200, r.text
    assert len(r.json()["grants"]) == 1
