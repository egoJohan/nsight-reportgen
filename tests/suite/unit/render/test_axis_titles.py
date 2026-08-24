"""Axis titles: the fourth of P-C-27's four editable text properties.

Requirement P-C-27 asks that a chart's title, subtitle, value names and AXIS
names all be editable in the design view. The first three were; axis names had
only an on/off toggle and no text anywhere.
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from reportbuilder.model.report import (  # noqa: E402
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.render.image._mpl import apply_axis_titles  # noqa: E402


def _spec(**kw) -> ChartSpec:
    kw.setdefault("elements", ElementToggles())
    return ChartSpec(
        question_ref="q1", chart_type="bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="s1", **kw)


def _axes():
    return plt.subplots()[1]


def test_axis_titles_default_to_empty():
    spec = _spec()
    assert spec.axis_x_title == ""
    assert spec.axis_y_title == ""


def test_axis_titles_round_trip():
    spec = _spec(axis_x_title="Ikäryhmä", axis_y_title="Osuus vastaajista")
    assert spec.axis_x_title == "Ikäryhmä"
    assert spec.axis_y_title == "Osuus vastaajista"


def test_the_image_renderer_draws_them():
    """The compositor path is what the Design preview shows."""
    ax = _axes()
    apply_axis_titles(ax, _spec(axis_x_title="X label", axis_y_title="Y label"), "#222222")
    assert ax.get_xlabel() == "X label"
    assert ax.get_ylabel() == "Y label"


def test_an_unset_axis_title_draws_nothing():
    ax = _axes()
    apply_axis_titles(ax, _spec(axis_x_title="Only X"), "#222222")
    assert ax.get_xlabel() == "Only X"
    assert ax.get_ylabel() == ""


def test_the_axis_names_toggle_still_governs():
    """One control means "no axis text on this slide", as it always did."""
    ax = _axes()
    apply_axis_titles(
        ax,
        _spec(axis_x_title="X label", axis_y_title="Y label",
              elements=ElementToggles(axis_names=False)),
        "#222222")
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""


def test_it_survives_a_chart_family_with_no_axis_titles_set():
    """Pie and friends call nothing here; a spec with no titles must be a no-op."""
    ax = _axes()
    apply_axis_titles(ax, _spec(), "#222222")
    assert ax.get_xlabel() == ""
    assert ax.get_ylabel() == ""


def test_the_preview_request_carries_them_to_the_chart_spec():
    """The regression that a green unit test missed.

    Both renderers drew axis titles correctly while the live preview showed
    none: the preview builds its ChartSpec from a Pydantic request model, which
    silently drops fields it does not declare. Only rendering a slide and
    LOOKING at it caught that, so the seam gets a test of its own.
    """
    from reportbuilder.api.routes_questions import ChartSpecBody, _chart_spec_from_body

    body = ChartSpecBody(
        question_ref="q1", chart_type="bar",
        axis_x_title="Osuus vastaajista (%)", axis_y_title="Vastausvaihtoehto")
    spec = _chart_spec_from_body(body)
    assert spec.axis_x_title == "Osuus vastaajista (%)"
    assert spec.axis_y_title == "Vastausvaihtoehto"


# ---------------------------------------------------------------------------
# Which charts actually draw them.
#
# The helper was written once and wired into the bar builders only, so on a line
# or a scatter the author typed an axis name, saw the field keep it, and got a
# chart without it. Nothing said the chart type was the reason.
# ---------------------------------------------------------------------------

_AXED = ["vertical_bar", "horizontal_bar", "stacked_vertical_bar",
         "stacked_horizontal_bar", "line", "scatter", "combo"]


def _drawn_labels(chart_type: str, monkeypatch) -> tuple[str, str]:
    """Render a real chart of this type and read the axis labels off the figure.

    Read at render time, through the builder's own `render_png`, because the
    builder closes its figure on the way out — and read off the AXES rather than
    checked by spying on the helper, since "the builder called something" is not
    the claim. The claim is that the words reach the picture.
    """
    import sys

    from reportbuilder.render.image import IMAGE_BUILDERS
    from suite._helpers import make_ctx
    from suite.integration.render._series import series_for

    module = sys.modules[IMAGE_BUILDERS[chart_type].__module__]
    seen: dict[str, tuple[str, str]] = {}
    original = module.render_png

    def spy(fig, *a, **k):
        ax = fig.axes[0]
        seen["labels"] = (ax.get_xlabel(), ax.get_ylabel())
        return original(fig, *a, **k)

    monkeypatch.setattr(module, "render_png", spy)

    series, extra = series_for(chart_type)
    kw = dict(axis_x_title="Ikäryhmä", axis_y_title="Osuus vastaajista", **extra)
    _prs, _slide, _slot, ctx = make_ctx(chart_type, series, **kw)
    IMAGE_BUILDERS[chart_type](ctx)
    return seen.get("labels", ("<never rendered>", ""))


def test_every_chart_with_axes_draws_the_authors_axis_names(monkeypatch):
    missing = [t for t in _AXED
               if _drawn_labels(t, monkeypatch) != ("Ikäryhmä", "Osuus vastaajista")]
    assert missing == [], f"axis titles typed but never drawn on: {missing}"
