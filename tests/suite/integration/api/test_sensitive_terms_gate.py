"""A report cannot be created until somebody says which names must be masked.

Creating a report is what turns on headline generation, theme summarisation and
overview bullets — every one of which sends the study's own wording to an LLM.
The terms to pseudonymise are proposed from the study's structure, but a person
confirms them, because "Ahne" ("greedy") and "Validia" are both capitalised
battery members and only a human tells the image attribute from the care
provider.

The gate is on report CREATION rather than on the LLM call: one checkpoint,
where somebody is present and deciding, instead of a check on every code path
that might one day reach a model.
"""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def brand_study_bytes(tmp_path):
    """A study shaped like a real brand tracker: a battery whose members are
    the brands. The plain synthetic fixture names no companies, so it proposes
    nothing — and a gate that only fires on studies with something to review
    would never fire on it."""
    import pandas as pd
    import pyreadstat

    df = pd.DataFrame({"b1": [1.0, 2.0, 1.0], "b2": [2.0, 1.0, 2.0],
                       "b3": [1.0, 1.0, 2.0]})
    path = tmp_path / "brands.sav"
    pyreadstat.write_sav(
        df, str(path),
        column_labels=["Attendo:Mitä seuraavista tunnet?",
                       "Esperi:Mitä seuraavista tunnet?",
                       "Humana:Mitä seuraavista tunnet?"],
        variable_value_labels={c: {1: "Kyllä", 2: "Ei"} for c in df.columns},
        variable_measure={c: "nominal" for c in df.columns})
    return path.read_bytes()


@pytest.fixture
def case_with_data(client_memory, brand_study_bytes):
    cid = client_memory.post("/customers", json={"name": "Asiakas"}).json()["id"]
    kid = client_memory.post(f"/customers/{cid}/cases",
                             json={"name": "Tutkimus"}).json()["id"]
    mid = client_memory.post(
        f"/cases/{kid}/materials",
        files={"file": ("s.sav", brand_study_bytes, "application/octet-stream")},
    ).json()["material_id"]
    return client_memory, kid, mid


def _new_report(client, kid):
    return client.post(f"/cases/{kid}/reports",
                       json={"name": "R", "render_mode": "image",
                             "template_ref": "", "charts": []})


def test_a_report_is_refused_until_the_terms_are_accepted(case_with_data):
    client, kid, _mid = case_with_data
    refused = _new_report(client, kid)
    assert refused.status_code == 409, refused.text
    assert "company names" in refused.json()["detail"].lower()
    assert "accept them" in refused.json()["detail"].lower()


def test_the_terms_are_proposed_from_the_study_itself(case_with_data):
    client, _kid, mid = case_with_data
    r = client.get(f"/materials/{mid}/sensitive-terms")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"Attendo", "Esperi", "Humana"} <= set(body["proposed"])
    assert body["accepted"] is None, "nobody has reviewed them yet"


def test_a_study_that_names_no_companies_is_not_gated(client_memory, synthetic_bytes):
    """Nothing identified means nothing to show and nothing to accept. Gating
    it would be a gate on the fixture rather than on the risk."""
    cid = client_memory.post("/customers", json={"name": "A"}).json()["id"]
    kid = client_memory.post(f"/customers/{cid}/cases",
                             json={"name": "K"}).json()["id"]
    client_memory.post(f"/cases/{kid}/materials",
                       files={"file": ("s.sav", synthetic_bytes,
                                       "application/octet-stream")})
    assert _new_report(client_memory, kid).status_code == 200


def test_accepting_them_opens_the_gate(case_with_data):
    client, kid, mid = case_with_data
    accepted = client.put(f"/materials/{mid}/sensitive-terms",
                          json={"terms": ["Attendo", "Esperi"]})
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["accepted"] == ["Attendo", "Esperi"]

    made = _new_report(client, kid)
    assert made.status_code == 200, made.text


def test_accepting_an_empty_list_is_a_real_answer(case_with_data):
    """"I looked; this study names no companies" must pass. It is a different
    statement from never having looked, which is what the gate refuses."""
    client, kid, mid = case_with_data
    assert client.put(f"/materials/{mid}/sensitive-terms",
                      json={"terms": []}).status_code == 200
    assert _new_report(client, kid).status_code == 200


def test_it_records_who_accepted_them_and_when(case_with_data):
    """This list decides what is masked before text reaches a model. If a name
    later leaks, the first question is who accepted the list that omitted it."""
    client, _kid, mid = case_with_data
    client.put(f"/materials/{mid}/sensitive-terms", json={"terms": ["Attendo"]})
    body = client.get(f"/materials/{mid}/sensitive-terms").json()
    assert body["accepted"] == ["Attendo"]
    assert body["accepted_at"], "no timestamp"
    assert body["accepted_by"], "no author"


def test_longer_terms_are_stored_first(case_with_data):
    """"Esperi Care Oy" must be substituted before "Esperi", or the shorter
    match leaves " Care Oy" stranded beside a surrogate."""
    client, _kid, mid = case_with_data
    r = client.put(f"/materials/{mid}/sensitive-terms",
                   json={"terms": ["Esperi", "Esperi Care Oy", "Attendo"]})
    assert r.json()["accepted"][0] == "Esperi Care Oy"


def test_a_case_with_no_material_is_not_blocked(client_memory):
    """Nothing to analyse means nothing to leak."""
    cid = client_memory.post("/customers", json={"name": "A"}).json()["id"]
    kid = client_memory.post(f"/customers/{cid}/cases",
                             json={"name": "K"}).json()["id"]
    assert _new_report(client_memory, kid).status_code == 200
