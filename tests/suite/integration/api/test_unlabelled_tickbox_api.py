"""The grouping editor sees an unlabelled tick-box, and can group it.

Two seams, and both are needed. `/variables` marks the pool the dialog draws;
`/regroup` is where the group the analyst then makes is reshaped. Miss either
and the study still looks empty, or the group vanishes with no message.

Reported from staging: 272 variables in the Kaiutinboksi study, 269 of them
unlabelled, and Manage grouping offered nothing at all. (Johan, 2026-09-11)
"""
from __future__ import annotations

import pytest

from reportbuilder.testing.fixtures import unlabelled_tickbox_sav_bytes

TICKS = {"Hyvatarjous", "Myyjansuositus", "Akt_IPTV"}


@pytest.fixture
def material(client_memory) -> str:
    cust = client_memory.post("/customers", json={"name": "AnonyymiYhtio"}).json()["id"]
    case = client_memory.post(f"/customers/{cust}/cases",
                              json={"name": "Kaiutinboksi"}).json()["id"]
    return client_memory.post(
        f"/cases/{case}/materials",
        files={"file": ("k.sav", unlabelled_tickbox_sav_bytes(),
                        "application/octet-stream")},
    ).json()["material_id"]


def test_the_pool_offers_every_unlabelled_tickbox(client_memory, material):
    vs = {v["name"]: v for v in client_memory
          .get(f"/materials/{material}/variables?include_all=true").json()["variables"]}
    assert {n for n, v in vs.items() if v["tickbox"]} == TICKS


def test_a_single_choice_and_a_measure_stay_out_of_the_pool(client_memory, material):
    """The widening must add tick-boxes, not sweep in everything unlabelled:
    Gender is coded 1/2 and Age is continuous."""
    vs = {v["name"]: v for v in client_memory
          .get(f"/materials/{material}/variables?include_all=true").json()["variables"]}
    assert vs["Gender"]["tickbox"] is False
    assert vs["Age"]["tickbox"] is False


def test_the_preview_accepts_the_group_the_analyst_makes(client_memory, material):
    """The dialog's cards come from here. Called without the data, a group of
    unlabelled tick-boxes was silently dropped: the analyst pressed the button
    and nothing appeared."""
    r = client_memory.post(f"/materials/{material}/regroup", json={
        "groups": [{"kind": "multi",
                    "variables": ["Hyvatarjous", "Myyjansuositus"],
                    "label": "Syyt hankintaan"}],
        "singles": [], "comparisons": []})
    assert r.status_code == 200, r.text
    combo = [q for q in r.json()["questions"]
             if q["kind"] == "multi"
             and set(q["variables"]) == {"Hyvatarjous", "Myyjansuositus"}]
    assert combo, [q["qid"] for q in r.json()["questions"]]
    assert combo[0]["text"] == "Syyt hankintaan"


def test_a_group_of_non_tickboxes_is_still_refused(client_memory, material):
    """Unchanged: a group naming Gender is skipped, not honoured."""
    r = client_memory.post(f"/materials/{material}/regroup", json={
        "groups": [{"kind": "multi", "variables": ["Gender", "Hyvatarjous"]}],
        "singles": [], "comparisons": []})
    assert r.status_code == 200
    assert not any(q["kind"] == "multi" and "Gender" in q["variables"]
                   for q in r.json()["questions"])
