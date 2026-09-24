"""The template's layout, as an author can see and correct it.

Harvesting a customer's .pptx is a guess made from a file nobody wrote for us,
and on the three templates we have it was wrong three different ways: Arla's
white title colour was discarded and drawn black on a black band, its every
layout is two-column so the chart went into a half-width box, Prima Pet's
representative slide carries a 2.61in title box that pushed the question and
the chart down the slide.

The rules are better now. The next template will be unusual in some new way,
so these endpoints let an author say what the answer is — per template, because
each of those faults is a property of the template rather than of one report.
"""
import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def customer_with_template(client_memory):
    from reportbuilder.render.default_template import default_template_bytes
    house_template_bytes = default_template_bytes()
    cid = client_memory.post("/customers", json={"name": "Asiakas"}).json()["id"]
    up = client_memory.post(
        f"/customers/{cid}/templates",
        files={"file": ("pohja.pptx", house_template_bytes,
                        "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
    )
    assert up.status_code == 201, up.text
    return client_memory, cid, up.json()["id"]


def test_it_reports_the_layouts_an_author_could_choose(customer_with_template):
    client, cid, tid = customer_with_template
    body = client.get(f"/customers/{cid}/templates/{tid}/layout").json()
    assert body["layouts"], "a template has layouts to choose between"
    assert all({"index", "name", "content_pct", "suitable"} <= set(l)
               for l in body["layouts"])
    assert body["slide"]["w"] > 0 and body["slide"]["h"] > 0


def test_it_reports_what_was_harvested(customer_with_template):
    client, cid, tid = customer_with_template
    harvested = client.get(f"/customers/{cid}/templates/{tid}/layout").json()["harvested"]
    assert set(harvested["title"]) == {"x", "y", "w", "h", "font", "size", "colour"}
    assert set(harvested["content"]) == {"x", "y", "w", "h", "font", "size", "colour"}


def test_nothing_is_overridden_to_begin_with(customer_with_template):
    client, cid, tid = customer_with_template
    assert client.get(f"/customers/{cid}/templates/{tid}/layout").json()["overrides"] == {}


def test_an_override_is_saved_and_read_back(customer_with_template):
    client, cid, tid = customer_with_template
    saved = client.put(f"/customers/{cid}/templates/{tid}/layout",
                       json={"layout_index": 3,
                             "title": {"colour": "FFFFFF", "size": 20},
                             "content": {"x": 0.5, "y": 1.75, "w": 12.3, "h": 5.0},
                             "accent": "FF5000"})
    assert saved.status_code == 200, saved.text
    back = client.get(f"/customers/{cid}/templates/{tid}/layout").json()["overrides"]
    assert back["layout_index"] == 3
    assert back["title"] == {"colour": "FFFFFF", "size": 20.0}
    assert back["content"] == {"x": 0.5, "y": 1.75, "w": 12.3, "h": 5.0}
    assert back["accent"] == "FF5000"


def test_blank_fields_are_not_stored_as_opinions(customer_with_template):
    """"Inherit" is the absence of a value, not a value meaning nothing — or
    every reader would have to recognise the difference."""
    client, cid, tid = customer_with_template
    client.put(f"/customers/{cid}/templates/{tid}/layout",
               json={"title": {"colour": "", "size": 0}, "content": {}, "accent": ""})
    assert client.get(f"/customers/{cid}/templates/{tid}/layout").json()["overrides"] == {}


def test_sub_stands_in_the_contents_corner_by_default(customer_with_template):
    """SUB's default box is the content's own top-left corner, and the chart
    starts where SUB ends. One line tall, from the size the template states:
    the box is geometry an author drags, so it cannot depend on what any one
    slide's question says. (Johan, 2026-09-21)"""
    client, cid, tid = customer_with_template
    h = client.get(f"/customers/{cid}/templates/{tid}/layout").json()["harvested"]
    sub, content = h["subtitle"], h["content"]
    assert sub["x"] == pytest.approx(content["x"], abs=0.01), "the same left edge"
    assert sub["w"] == pytest.approx(content["w"], abs=0.01), "the same width"
    assert 0.2 <= sub["h"] <= 0.6, f"one line, not {sub['h']}in"
    # Stacked, not on top of each other: the content starts where SUB ends.
    assert content["y"] == pytest.approx(sub["y"] + sub["h"], abs=0.01), (
        f"content starts at {content['y']}in, SUB ends at {sub['y'] + sub['h']}in")
    assert content["h"] > 1.0, "the chart still has room under it"


def test_the_boxes_are_reported_without_drawing_a_chart(customer_with_template,
                                                        monkeypatch):
    """The areas are what an author waits for on every change of the layout
    dropdown, and a chart was rendered on the way to answering — to ask where
    the footer goes, which `footer_top` reads off the layout and never off what
    was drawn. Reported as "the refresh takes a long time". (2026-09-21)"""
    from reportbuilder.export import pptx_build

    def never(*a, **k):
        raise AssertionError("the layout endpoint rendered a slide")

    monkeypatch.setattr(pptx_build, "build_presentation", never)
    client, cid, tid = customer_with_template
    r = client.get(f"/customers/{cid}/templates/{tid}/layout")
    assert r.status_code == 200, r.text
    footer = r.json()["harvested"]["footer"]
    slide_h = r.json()["slide"]["h"]
    assert 0 < footer["y"] < slide_h, "the footer still lands on the slide"
