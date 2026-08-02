"""Per-chart identity. Charts were identified by question_ref, so one question
could not own two slides — which a comparison section requires.
(spec 2026-08-02-compare-groups-section §3)"""
from __future__ import annotations

import json
from dataclasses import replace

from reportbuilder.model.report import Report, report_from_json, report_to_json
from reportbuilder.testing.fixtures import _chart


def _doc(*charts) -> dict:
    """A report as JSON, the way a stored report arrives."""
    r = Report(name="R", render_mode="native", template_ref="t.pptx", charts=charts)
    return json.loads(report_to_json(r))


def _strip(doc: dict, key: str) -> dict:
    """A report written BEFORE the field existed."""
    for c in doc["charts"]:
        c.pop(key, None)
    return doc


def test_a_missing_slide_id_stays_empty():
    """The backend deliberately does NOT backfill: assigning an id on load would
    make report_from_json(report_to_json(r)) != r for a code-built report and break
    round-trip equality. The editor assigns ids when it loads a report."""
    doc = _strip(_doc(_chart("a", slot="s1"), _chart("b", slot="s2")), "slide_id")
    assert [c.slide_id for c in report_from_json(doc).charts] == ["", ""]


def test_loading_an_old_report_is_still_an_exact_round_trip():
    """The invariant the backfill would have broken."""
    doc = _strip(_doc(_chart("a", slot="s1"), _chart("a", slot="s2")), "slide_id")
    once = report_from_json(doc)
    assert report_from_json(json.loads(report_to_json(once))) == once


def test_distinct_ids_survive_for_two_charts_on_one_question():
    doc = _doc(replace(_chart("a", slot="s1"), slide_id="x1"),
               replace(_chart("a", slot="s2"), slide_id="x2"))
    ids = [c.slide_id for c in report_from_json(doc).charts]
    assert ids == ["x1", "x2"]


def test_an_explicit_slide_id_is_preserved():
    doc = _doc(replace(_chart("a"), slide_id="keep-me"))
    assert report_from_json(doc).charts[0].slide_id == "keep-me"


def test_compare_group_round_trips():
    doc = _doc(replace(_chart("a"), compare_group="polku"))
    r = report_from_json(doc)
    assert r.charts[0].compare_group == "polku"
    again = report_from_json(json.loads(report_to_json(r)))
    assert again.charts[0].compare_group == "polku"


def test_compare_group_defaults_to_none():
    doc = _strip(_doc(_chart("a")), "compare_group")
    assert report_from_json(doc).charts[0].compare_group is None


def test_both_fields_survive_a_canonicalising_round_trip():
    """routes_reports canonicalises on save: from_json -> to_json. A field the
    model does not know is silently dropped, so these must be real fields."""
    doc = _doc(replace(_chart("a"), slide_id="s1", compare_group="polku"))
    out = json.loads(report_to_json(report_from_json(doc)))
    assert out["charts"][0]["slide_id"] == "s1"
    assert out["charts"][0]["compare_group"] == "polku"


def test_assigned_ids_are_stable_across_a_save_and_reload():
    doc = _doc(replace(_chart("a", slot="s1"), slide_id="x1"),
               replace(_chart("a", slot="s2"), slide_id="x2"))
    once = report_from_json(doc)
    twice = report_from_json(json.loads(report_to_json(once)))
    assert [c.slide_id for c in once.charts] == [c.slide_id for c in twice.charts]


# ---- the blank special slide -----------------------------------------------
# An author-written slide: a heading plus markdown bullets, no AI. It rides the
# existing special-slide machinery, so it must be a recognised special type or
# the renderer would try to compute a data series for it.

def test_special_blank_is_a_special_slide():
    from reportbuilder.model.report import (
        SPECIAL_SLIDE_TYPES, is_special_slide, renders_as_bullets,
    )
    from dataclasses import replace as _replace

    assert "special_blank" in SPECIAL_SLIDE_TYPES
    blank = _replace(_chart("sp_blank_1"), chart_type="special_blank")
    assert is_special_slide(blank) is True
    assert renders_as_bullets(blank) is True


def test_a_blank_slide_round_trips_with_its_bullets():
    from dataclasses import replace as _replace

    blank = _replace(_chart("sp_blank_1"), chart_type="special_blank",
                     slide_title="Omat huomiot",
                     options={"bullets": ["* eka", "  * sisennetty"]})
    out = report_from_json(_doc(blank)).charts[0]
    assert out.chart_type == "special_blank"
    assert out.slide_title == "Omat huomiot"
    assert out.options["bullets"] == ["* eka", "  * sisennetty"]
