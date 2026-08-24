"""Deleting a study while somebody has a report in it open.

The single-report delete refuses while another person is editing. The case
delete removes EVERY report in the study and asked nothing, so the report being
edited went anyway, along with everything beside it — a lost edit is
recoverable from the author's screen, a lost study is not.

Driven through the route. The first version of this test rebuilt the guard's
own filtering inside the test and asserted on that; it passed with the guard
deleted from `delete_case` outright, which is the one thing a test like this
exists to catch.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User

pytestmark = pytest.mark.integration


def _sign_in_as(client, repo, auth, email, *grants, admin=False):
    from reportbuilder.api.deps_auth import current_user

    user = repo.save_user(auth, User(id="", email=email, name=email.split("@")[0],
                                     is_admin=admin,
                                     grants=tuple(Grant(s, m) for s, m in grants)))
    client.app.dependency_overrides[current_user] = lambda: user
    return user


@pytest.fixture
def study(client_memory):
    from reportbuilder.api.deps_store import get_auth, get_repository

    overrides = client_memory.app.dependency_overrides
    repo, auth = overrides[get_repository](), overrides[get_auth]()
    cid = client_memory.post("/customers", json={"name": "Asiakas"}).json()["id"]
    kid = client_memory.post(f"/customers/{cid}/cases",
                             json={"name": "Tutkimus"}).json()["id"]
    rid = client_memory.post(f"/cases/{kid}/reports",
                             json={"name": "R", "render_mode": "image",
                                   "template_ref": "", "charts": []}).json()["report_id"]
    return client_memory, repo, auth, cid, kid, rid


def test_a_colleagues_open_report_stops_the_study_being_deleted(study):
    client, repo, auth, cid, kid, rid = study
    johan = _sign_in_as(client, repo, auth, "johan@egoiq.com", (cid, "edit"))
    assert client.post(f"/cases/{kid}/reports/{rid}/lock?tab=a").status_code == 200

    _sign_in_as(client, repo, auth, "maija@egoiq.com", (cid, "edit"))
    refused = client.delete(f"/cases/{kid}")
    assert refused.status_code == 409, refused.text
    assert "johan" in refused.json()["detail"].lower()

    # And the study is still there, with its report.
    assert client.get(f"/cases/{kid}/reports").json()["reports"], "the study went anyway"
    assert johan.id


def test_the_person_holding_it_can_still_delete_their_own_study(study):
    """The guard must not bar somebody from their own work."""
    client, repo, auth, cid, kid, rid = study
    _sign_in_as(client, repo, auth, "johan@egoiq.com", (cid, "edit"), admin=True)
    assert client.post(f"/cases/{kid}/reports/{rid}/lock?tab=a").status_code == 200

    gone = client.delete(f"/cases/{kid}")
    assert gone.status_code in (200, 409), gone.text
    if gone.status_code == 409:
        # datahive's consent gate, not the lock guard — those are different
        # 409s and only one of them names a person.
        assert "editing" not in str(gone.json().get("detail", "")).lower()
