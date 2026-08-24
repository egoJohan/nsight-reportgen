"""Choosing a template, then saving — the author's own two actions in a row.

This was a guaranteed lockout. The editor held the version it loaded and sent
it as If-Match on every save; binding a template writes the report document
server-side (routes_templates.bind_report_template -> save_report), which moved
that version with nothing telling the editor. The autosave 1.5 s later was
refused as "saved by somebody else", and ReportWizard.save() reads a 409 as
"the report changed hands" — so it closed the editor and dropped every edit
since the last successful save. No second person involved; it reproduced every
time somebody picked a pohja from the toolbar.

The editor no longer sends If-Match at all (web/src/lib/api.ts says why). What
guards concurrent editing is the lock. The server still HONOURS If-Match for a
caller that opts in, and the second test here holds that contract — but nothing
in the app opts in, so it cannot lock anybody out of their own work.
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
    return client_memory, cid, kid, rid


def test_binding_a_template_does_not_invalidate_the_open_editors_version(report):
    client, cid, kid, rid = report

    # The editor opens the report — exactly as the wizard does.
    doc = client.get(f"/cases/{kid}/reports/{rid}").json()

    # The author picks a template from the toolbar. Same person, same session.
    bound = client.put(
        f"/customers/{cid}/cases/{kid}/reports/{rid}/template",
        json={"template_id": None})
    assert bound.status_code == 200, bound.text

    # The autosave that follows a second later, sending what the wizard sends.
    saved = client.put(f"/cases/{kid}/reports/{rid}", json=dict(doc, name="Still mine"))
    assert saved.status_code == 200, (
        "the author's own template change locked them out of their own report: "
        f"{saved.status_code} {saved.text}")
    assert client.get(f"/cases/{kid}/reports/{rid}").json()["name"] == "Still mine"


def test_the_server_still_refuses_a_save_that_names_a_version_it_has_passed(report):
    """The contract kept for a caller that opts in — an integration, a script,
    or a future editor that can refresh its version on every write path."""
    client, _cid, kid, rid = report
    r = client.get(f"/cases/{kid}/reports/{rid}")
    doc, tag = r.json(), r.headers["ETag"].strip('"')

    assert client.put(f"/cases/{kid}/reports/{rid}", json=dict(doc, name="Theirs"),
                      headers={"If-Match": tag}).status_code == 200
    late = client.put(f"/cases/{kid}/reports/{rid}", json=dict(doc, name="Mine"),
                      headers={"If-Match": tag})
    assert late.status_code == 409
