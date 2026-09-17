"""A radar's ring numbers are drawn where the polygon is NOT.

matplotlib puts the radial tick labels on a fixed diagonal, and the polygon
goes wherever the data goes, so the two met: on the brand-awareness radar the
"15" was drawn straight through the polygon's edge, its digits crossed by a
2.4pt blue line. The labels that say what the rings are worth are the one part
of a radar a reader consults deliberately.

Nothing about the fixed angle was chosen — it is matplotlib's default. The
angle that IS chosen is the one where the data reaches least far, measured
between two spokes so the numbers do not sit on a spoke line either.
"""
from __future__ import annotations

import math

import pandas as pd
import pytest
from pptx import Presentation
from pptx.util import Inches

from reportbuilder.ingest.sav_reader import ValueLabel, Variable
from reportbuilder.model.question import Question, QuestionModel
from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.stats.engine import compute
import reportbuilder.render.image.radar as R

_CATS = ["Amazon", "Salesforce", "Aramco", "nSight", "Estrella", "En osaa sanoa"]


def _rlabel_position(counts: list[int]) -> float:
    """The angle, in degrees, the finished radar puts its ring numbers at."""
    var = Variable(name="q", label="Mitä yrityksiä tunnet?", measurement="nominal",
                   missing_values=[],
                   value_labels=[ValueLabel(value=float(i + 1), label=c)
                                 for i, c in enumerate(_CATS)])
    rows = [{"q": float(i + 1)} for i, n in enumerate(counts) for _ in range(n)]
    model = QuestionModel(
        variables={"q": var},
        questions=[Question(qid="q", text=var.label, kind="single", variables=("q",))])
    spec = ChartSpec(question_ref="q", chart_type="radar", statistic="pct",
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
    original = R.render_png

    def _spy(fig):
        seen["pos"] = float(fig.axes[0].get_rlabel_position())
        return original(fig)

    R.render_png = _spy
    try:
        R.build_image_radar(ctx)
    finally:
        R.render_png = original
    return seen["pos"]


def _apart(a: float, b: float) -> float:
    """Smallest angle between two bearings, in degrees."""
    return abs((a - b + 180.0) % 360.0 - 180.0)


#: Category 0 sits at 0 degrees, and each subsequent one 360/6 further round.
_SPOKE = 360.0 / len(_CATS)


def _best_gaps(counts: list[int]) -> list[float]:
    """The gap midpoints whose two neighbouring spokes reach least far.

    This is the contract, not a particular angle: whichever gap the data leaves
    emptiest is where the ring numbers belong.
    """
    n = len(counts)
    reach = {i * _SPOKE: c for i, c in enumerate(counts)}
    spokes = sorted(reach)
    scored = []
    for i, a in enumerate(spokes):
        b = spokes[(i + 1) % n]
        mid = (a + _SPOKE / 2.0) % 360.0
        scored.append((max(reach[a], reach[b]), mid))
    best = min(sc for sc, _m in scored)
    return [m for sc, m in scored if sc == best]


@pytest.mark.parametrize("counts", [
    [300, 20, 20, 20, 20, 20],
    [20, 20, 20, 300, 20, 20],
    [10, 20, 30, 40, 50, 300],
    [10, 20, 30, 40, 50, 60],
])
def test_the_numbers_go_where_the_data_reaches_least_far(counts):
    pos = _rlabel_position(counts)
    best = _best_gaps(counts)
    assert min(_apart(pos, m) for m in best) < 1.0, (
        f"ring numbers at {pos}° for {counts}; the emptiest gaps are {best}")


def test_the_numbers_sit_between_spokes_not_on_one():
    """A spoke line runs under its own angle; the numbers go in the gap."""
    pos = _rlabel_position([300, 20, 20, 20, 20, 20])
    nearest = min((_apart(pos, i * _SPOKE) for i in range(len(_CATS))))
    assert nearest > _SPOKE * 0.25, f"{pos}° is on top of a spoke"


def test_a_flat_radar_still_answers_something_sane():
    pos = _rlabel_position([100, 100, 100, 100, 100, 100])
    assert 0.0 <= pos < 360.0, pos
