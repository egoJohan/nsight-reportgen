"""The panels endpoint says which groups the slide was actually drawn on.

A slide can be narrowed to some of its classifier's groups. That used to be
disclosed in the deck's own footer, read from `SeriesResult.applied_filter` —
the engine's account of what it applied. `edc4964` moved the disclosure into the
editor and, in doing so, changed where the answer came from: the warning
compared the author's `classifying_values` against `drawn + thin + capped`.

Those can never disagree. The endpoint computes on data already narrowed to
`classifying_values` (`_selected_rows`), so it only ever reports the picked
groups back — `picked < drawn+thin+capped` is false by construction, and the
warning was dead in the one case it was written for. Where it DID fire, it was
wrong: a slide whose `classifying_values` name groups of a classifier the author
has since changed got a confident "this slide counts Design 1, Design 3 and
nobody else" while the slide was the whole sample split by sex.

`applied_filter` already holds the right answer and was being read by nothing.
So the endpoint reports it, and the editor states a fact instead of inferring
one from arithmetic that cannot support it. (Johan, 2026-09-17)
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _panels(client, qid, var, values=None):
    params = {"classifying_var": var}
    if values is not None:
        params["classifying_values"] = values
    r = client.get(f"/materials/{client.material_id}/questions/{qid}/panels",
                   params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _first_split_question(client) -> tuple[str, str, list[str]]:
    """A question, a classifier, and the classifier's own group names.

    Taken from `drawn + thin`, not from `drawn`: the fixture's sample is small
    enough that every group is under the reporting floor, so `drawn` is just
    `Total`. Which groups are big enough to CHART is a different question from
    which groups the slide was narrowed to, and this test is about the second.
    """
    qs = client.get(f"/materials/{client.material_id}/questions").json()["questions"]
    variables = client.get(
        f"/materials/{client.material_id}/variables").json()["variables"]
    for v in variables:
        if not v.get("segmentable"):
            continue
        for q in qs:
            got = _panels(client, q["qid"], v["name"])
            groups = [g for g in list(got["drawn"]) + list(got["thin"])
                      if g != "Total"]
            if got["split"] and len(groups) >= 2:
                return q["qid"], v["name"], groups
    pytest.skip("no question in the fixture splits into two groups")


def test_a_whole_slide_reports_no_narrowing(client_mock):
    qid, var, _drawn = _first_split_question(client_mock)
    assert _panels(client_mock, qid, var)["narrowed_to"] == []


def test_a_narrowed_slide_names_the_groups_it_kept(client_mock):
    """The case the editor warning could never see."""
    qid, var, drawn = _first_split_question(client_mock)
    picked = drawn[:1]
    got = _panels(client_mock, qid, var, picked)
    assert got["narrowed_to"] == picked


def test_picking_every_group_is_not_a_narrowing(client_mock):
    """Ticking all of them is the default state written out longhand, and an
    author who has excluded nobody must not be told they have."""
    qid, var, drawn = _first_split_question(client_mock)
    assert _panels(client_mock, qid, var, drawn)["narrowed_to"] == []


def test_a_name_the_data_does_not_have_is_not_reported(client_mock):
    """Stale `classifying_values` — left behind when the author changes the
    classifying variable — is exactly what made the old warning lie. The engine
    ignores names it cannot resolve, and this reports what the engine did, so a
    slide narrowed by nothing reports nothing."""
    qid, var, _drawn = _first_split_question(client_mock)
    assert _panels(client_mock, qid, var, ["Design 1", "Design 3"])["narrowed_to"] == []
