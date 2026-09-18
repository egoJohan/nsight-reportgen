"""A combo's category names do not print through each other.

Every bar builder measures its x tick labels against the column pitch and
wraps or rotates them when they do not fit — `build_image_column` always
rotates, `build_image_column_stacked` measures first. The combo did neither:
it set the names flat, at full length, whatever they were.

On Attendo's brand battery — fourteen statements like "Mahdollistaa hyvän
arjen" and "Tarjoaa laadukkaita hoivapalveluita" — that prints an unreadable
smear along the axis, each name straight through its neighbour. The overlap
oracle measured the same pair at 19.0px on every battery combo in the study.

Same lesson, same fix, applied to the one builder that had not had it.
"""
from __future__ import annotations

import pathlib
import sys

import pandas as pd
import pytest
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.stats.engine import compute
import reportbuilder.render.image.combo as C

# The project's own overlap rule, rather than a second one written here. A
# rotated label's axis-aligned bbox is far wider than its ink, so a plain box
# intersection calls rotated names collisions when they are not — the mistake
# `acceptance/oracles/overlap.py` was written to avoid. It measures each text
# flat and carries its angle, and it has the graze tolerance too.
_ACCEPTANCE = pathlib.Path(__file__).resolve().parents[4] / "acceptance"
if str(_ACCEPTANCE) not in sys.path:
    sys.path.insert(0, str(_ACCEPTANCE))
overlap = pytest.importorskip("oracles.overlap")

#: The customer's own statements, which is what makes them this long.
LONG = ["Mahdollistaa hyvän arjen", "Tarjoaa laadukkaita hoivapalveluita",
        "Tarjoaa monipuolista palvelua", "Inhimillinen", "Luotettava",
        "Välittävä", "Ammattitaitoinen", "Kohtelee ihmisiä arvostavasti",
        "Edelläkävijä", "Rehellinen", "Kehittää toimintatapojaan",
        "Välinpitämätön", "Ahne", "Kodikas"]
SHORT = ["Kyllä", "Ei", "EOS"]


def _tick_boxes(cats: list[str]) -> list:
    var = Variable(name="q", label="Mielikuva", measurement="nominal",
                   missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=c)
                                 for i, c in enumerate(cats)])
    rows = [{"q": float(i % len(cats) + 1)} for i in range(len(cats) * 40)]
    model = QuestionModel(
        variables={"q": var},
        questions=[Question(qid="q", text=var.label, kind="single", variables=("q",))])
    spec = ChartSpec(question_ref="q", chart_type="combo", statistic="pct",
                     classifying_var=None, number_format=NumberFormat(),
                     sort=SortSpec(basis="data_order"), template_slot="s1",
                     elements=ElementToggles())
    series = compute(model.question("q"), spec, pd.DataFrame(rows), model)
    prs = Presentation()
    ctx = RenderContext(slide=prs.slides.add_slide(prs.slide_layouts[6]),
                        slot=Slot(slide_index=0, left=Inches(0.5), top=Inches(1.4),
                                  width=Inches(11.6), height=Inches(4.0), name="s1"),
                        style=StyleSpec(), spec=spec, series=series,
                        fmt=spec.number_format)
    seen: dict = {}
    original = C.render_png

    def _spy(fig):
        fig.canvas.draw()
        seen["names"] = [t.get_text() for t in fig.axes[0].get_xticklabels()
                         if t.get_text()]
        seen["rotations"] = [round(t.get_rotation())
                             for t in fig.axes[0].get_xticklabels()]
        seen["collisions"] = [str(c) for c in overlap.collisions(fig)]
        return original(fig)

    C.render_png = _spy
    try:
        C.build_image_combo(ctx)
    finally:
        C.render_png = original
    return seen


def test_the_names_are_drawn_at_all():
    """Guards the tests below: no labels would trivially not collide."""
    assert len(_tick_boxes(LONG)["names"]) == len(LONG)


def test_long_names_do_not_print_through_each_other():
    hits = _tick_boxes(LONG)["collisions"]
    assert hits == [], f"{len(hits)} collisions, e.g. {hits[:3]}"


def test_long_names_are_rotated_to_achieve_that():
    """Says HOW, so a future change that stops colliding by dropping the names
    altogether does not pass."""
    assert all(r != 0 for r in _tick_boxes(LONG)["rotations"])


def test_short_names_are_left_flat():
    """Rotation costs vertical room and a little legibility, so it is only for
    names that need it. Three short words must stay exactly as they were."""
    got = _tick_boxes(SHORT)
    assert all(r == 0 for r in got["rotations"]), got["rotations"]
    assert got["collisions"] == []
