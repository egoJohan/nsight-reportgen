"""A save built on a copy somebody else has replaced is refused.

The editing lock normally stops two people getting this far. But it expires by
design — a crashed browser must not strand a report for ever — and that leaves
a window: one lock lapses, a colleague picks the report up and works on it, and
then the first tab saves the document it loaded hours ago. Saving is a
whole-document replace, so that is not a conflict to merge; it is every slide
the second person wrote, gone, with both saves returning 200.

An editor that says nothing about versions is not held to this, so older
clients and scripts behave exactly as before.
"""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def report(client_memory):
    cid = client_memory.post("/customers", json={"name": "Asiakas"}).json()["id"]
    kid = client_memory.post(f"/customers/{cid}/cases",
                             json={"name": "Tutkimus"}).json()["id"]
    rid = client_memory.post(f"/cases/{kid}/reports",
                             json={"name": "R", "render_mode": "image",
                                   "template_ref": "", "charts": []}).json()["report_id"]
    return client_memory, kid, rid


def _doc(client, kid, rid):
    r = client.get(f"/cases/{kid}/reports/{rid}")
    return r.json(), r.headers.get("ETag", "").strip('"')


def test_a_report_carries_its_version(report):
    client, kid, rid = report
    _doc_body, tag = _doc(client, kid, rid)
    assert tag.isdigit() and int(tag) >= 1


def test_saving_from_the_version_you_loaded_works(report):
    client, kid, rid = report
    doc, tag = _doc(client, kid, rid)
    doc["name"] = "Renamed"
    r = client.put(f"/cases/{kid}/reports/{rid}", json=doc, headers={"If-Match": tag})
    assert r.status_code == 200, r.text
    assert r.json()["version"] == int(tag) + 1


def test_saving_over_somebody_elses_work_is_refused(report):
    """Two editors, both starting from the same version."""
    client, kid, rid = report
    doc, tag = _doc(client, kid, rid)

    theirs = dict(doc, name="What the colleague wrote")
    assert client.put(f"/cases/{kid}/reports/{rid}", json=theirs,
                      headers={"If-Match": tag}).status_code == 200

    mine = dict(doc, name="What I had open since this morning")
    late = client.put(f"/cases/{kid}/reports/{rid}", json=mine,
                      headers={"If-Match": tag})
    assert late.status_code == 409, late.text
    assert "somebody else" in late.json()["detail"]

    # And theirs is what is actually stored.
    assert client.get(f"/cases/{kid}/reports/{rid}").json()["name"] == \
        "What the colleague wrote"


def test_an_editor_that_says_nothing_is_not_held_to_it(report):
    """Backwards compatibility, deliberately: a client that sends no version
    saves exactly as it did before."""
    client, kid, rid = report
    doc, _tag = _doc(client, kid, rid)
    client.put(f"/cases/{kid}/reports/{rid}", json=dict(doc, name="Someone else"))
    r = client.put(f"/cases/{kid}/reports/{rid}", json=dict(doc, name="No opinion"))
    assert r.status_code == 200, r.text


def test_saving_still_marks_the_stored_deck_as_no_longer_current(report):
    """Deliberately unchanged, and checked because the version now has to
    survive a save while nothing else does.

    Dropping `render_key` is how a save says the deck no longer matches the
    report — `rendered` means "an artefact exists for the report's CURRENT
    content" (repository._ref_from_meta). Carrying it across would make the
    Generated badge and the download offer a deck of something else.
    """
    from reportbuilder.api.deps_store import get_auth, get_repository

    client, kid, rid = report
    overrides = client.app.dependency_overrides
    repo, auth = overrides[get_repository](), overrides[get_auth]()
    case = repo.find_case(auth, kid)
    repo.save_render(auth, case.customer_id, case.id, rid, b"deck", "key-1")

    def ref():
        return next(r for r in repo.list_reports(auth, case.customer_id, case.id)
                    if r.id == rid)

    assert ref().rendered is True
    before = ref().version
    doc, tag = _doc(client, kid, rid)
    client.put(f"/cases/{kid}/reports/{rid}", json=dict(doc, name="Edited"),
               headers={"If-Match": tag})

    assert ref().rendered is False, "the stored deck is a deck of the old report"
    assert ref().version == before + 1, "but the version must survive the rewrite"
