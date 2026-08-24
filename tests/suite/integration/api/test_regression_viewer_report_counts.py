"""REGRESSION: a viewer's study card counts reports they are not shown.

`RepositoryClient.list_reports` now hides unrendered reports from a view-only
grant, but `/customers/{id}/cases` builds its "N drafts / N completed" badge
from `repo.list_reports_for_customer`, which does not. So a client sees a study
advertising three drafts, opens it, and finds an empty list — and the two
numbers used to agree, because a viewer used to be shown everything.
"""
import pytest

from reportbuilder.auth.permissions import Grant, User

pytestmark = pytest.mark.integration


def _become(client, email, *grants):
    from reportbuilder.api.deps_auth import current_user
    from reportbuilder.api.deps_store import get_auth, get_repository

    overrides = client.app.dependency_overrides
    repo, auth = overrides[get_repository](), overrides[get_auth]()
    user = repo.save_user(auth, User(id="", email=email, name="V",
                                     grants=tuple(Grant(s, m) for s, m in grants)))
    overrides[current_user] = lambda: user
    return user


def test_a_viewers_study_card_agrees_with_their_report_list(client_memory):
    cid = client_memory.post("/customers", json={"name": "Asiakas"}).json()["id"]
    kid = client_memory.post(f"/customers/{cid}/cases",
                             json={"name": "Tutkimus"}).json()["id"]
    for n in ("A", "B", "C"):
        client_memory.post(f"/cases/{kid}/reports",
                           json={"name": n, "render_mode": "image",
                                 "template_ref": "", "charts": []})

    _become(client_memory, "client@example.com", (cid, "view"))

    card = next(k for k in client_memory.get(f"/customers/{cid}/cases").json()
                if k["id"] == kid)
    listed = client_memory.get(f"/cases/{kid}/reports").json()["reports"]

    assert card["completed_reports"] + card["draft_reports"] == len(listed), (
        f"the card promises {card['completed_reports'] + card['draft_reports']} "
        f"report(s); the list has {len(listed)}")
