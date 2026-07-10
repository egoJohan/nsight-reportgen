"""Declarative config schema for chart plugins.

Each chart plugin declares an ordered list of :class:`ConfigField`s describing
the configuration knobs it exposes.  The frontend renders the config form purely
from this schema (via a widget registry), so a new chart type — even one with a
brand-new option — adds its field here and renders with no generic frontend
changes.

A ``widget`` names a control the frontend knows how to render:
``select`` · ``switch`` · ``number`` · ``variable`` · ``sort`` ·
``number_format`` · ``not_answered`` · ``category_labels`` · ``scatter_xy`` ·
``note``.  Data-bound widgets (``variable``/``not_answered``/``category_labels``)
pull what they need (the material's variables, the question's value labels) on
the frontend and self-hide when not applicable.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any


@dataclass(frozen=True)
class ConfigField:
    key: str                                  # ChartSpec field, or a key in ChartSpec.options
    widget: str                               # control type the frontend renders
    label: str = ""
    help: str | None = None
    options: tuple[tuple[str, str], ...] = ()  # (value, label) for select-like widgets
    default: Any = None
    required: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"key": self.key, "widget": self.widget, "label": self.label}
        if self.help is not None:
            d["help"] = self.help
        if self.options:
            d["options"] = [{"value": v, "label": lbl} for v, lbl in self.options]
        if self.default is not None:
            d["default"] = self.default
        if self.required:
            d["required"] = True
        return d


# --------------------------------------------------------------------------- #
# Shared option sets (mirror the labels the UI used; carried IN the schema so a
# future chart type can offer a different set without any frontend change).
# --------------------------------------------------------------------------- #
STATISTIC_OPTIONS = (
    ("pct", "Percentage"),
    ("count", "Count"),
    ("mean", "Mean"),
    ("median", "Median"),
    ("sum", "Sum"),
)

SORT_BASIS_OPTIONS = (
    ("pct", "Percentage"),
    ("data_order", "Survey order"),
    ("mean", "Mean"),
    ("count", "Count"),
)


# --------------------------------------------------------------------------- #
# Field factories — reusable building blocks for plugin schemas.
# --------------------------------------------------------------------------- #
def statistic_field() -> ConfigField:
    return ConfigField("statistic", "select", "Statistic",
                       options=STATISTIC_OPTIONS, default="pct")


def classifying_var_field(*, required: bool = False) -> ConfigField:
    return ConfigField(
        "classifying_var", "variable", "Classifying variable",
        help=(
            "Break the chart down by another variable (e.g. by gender or age) to "
            "get a series per group plus a Total." if not required else
            "Required: the dimension this chart splits its series by."
        ),
        required=required,
    )


def percent_base_field() -> ConfigField:
    # The cross-tab percentage DIRECTION. Only meaningful with a classifying
    # variable (the frontend self-hides it otherwise). "Automatic" resolves the
    # natural direction from the variables' roles; the others force it.
    return ConfigField(
        "percent_base", "select", "Percentages of",
        options=(("auto", "Automatic"),
                 ("classifier", "Each segment (the classifying variable)"),
                 ("question", "Each category (this question)"),
                 ("total", "Total")),
        default="auto",
        help=("Which sub-population each percentage is OF. 'Automatic' picks the "
              "natural direction (usually within each segment). 'Each category' "
              "instead distributes the segments within each of this question's "
              "categories — e.g. '% of men who fall in each group'."),
    )


def sort_field(*, stacked: bool = False) -> ConfigField:
    # The 'sort' widget renders both the basis (these options) and a separate
    # ascending/descending direction (descending is the default). Stacked bars add
    # "Top 2/3 sum": these reorder the BARS (classifier groups / battery statements) by
    # their summed two/three highest scale levels, while the scale stack stays 1..N.
    opts = SORT_BASIS_OPTIONS
    if stacked:
        opts = opts + (("topbox_sum", "Top 2 sum"), ("top3_sum", "Top 3 sum"))
    return ConfigField("sort", "sort", "Sort", options=opts, default="pct")


def number_format_field() -> ConfigField:
    return ConfigField("number_format", "number_format", "Number format", default="auto")


def show_not_answered_field() -> ConfigField:
    return ConfigField("show_not_answered", "switch", 'Show "Not answered"', default=False)


def empty_categories_field() -> ConfigField:
    return ConfigField("show_empty_categories", "switch", "Show empty (0%) categories",
                       default=True)


def not_answered_field() -> ConfigField:
    return ConfigField("not_answered_codes", "not_answered", '"Not answered" values')


def category_labels_field() -> ConfigField:
    return ConfigField("category_label_overrides", "category_labels", "Category labels")


def note_field(text: str) -> ConfigField:
    return ConfigField("note", "note", "", help=text)


def combo_secondary_field() -> ConfigField:
    return ConfigField(
        "combo_secondary", "numeric_variable", "Secondary variable (line)",
        help="A numeric/rating variable shown as a mean-per-category line on the "
             "right axis. Shares this question's categories as the x-axis.",
    )


# --------------------------------------------------------------------------- #
# Composed schemas shared by families of chart types.
# --------------------------------------------------------------------------- #
def _common_tail(*, sort_stacked: bool = False) -> tuple[ConfigField, ...]:
    """Knobs every data chart shares (after the classifying variable)."""
    return (
        sort_field(stacked=sort_stacked),
        number_format_field(),
        show_not_answered_field(),
        empty_categories_field(),
        not_answered_field(),
        category_labels_field(),
    )


def classifying_var_2_field() -> ConfigField:
    return ConfigField(
        "classifying_var_2", "variable", "Second classifying variable",
        help=(
            "Optionally split by a SECOND variable too (e.g. gender and age) — the "
            "chart shows one series per combination. Best kept to a few groups."
        ),
        required=False,
    )


def standard_schema() -> tuple[ConfigField, ...]:
    """Multi-series-capable charts: optional classifying variable."""
    # percent_base sits right after the statistic so the "Percentages of" direction
    # renders on the same row as "Statistic" (and self-hides for non-% statistics).
    return (statistic_field(), percent_base_field(), classifying_var_field(),
            *_common_tail())


def xtab_layout_field() -> ConfigField:
    return ConfigField(
        "xtab_layout", "select", "Two-variable layout",
        options=(("auto", "Automatic"), ("grouped", "Grouped bars"),
                 ("small_multiples", "Small multiples")),
        default="auto",
        help=("With a second classifying variable: 'Grouped bars' pulls the bars apart "
              "into groups by the first variable; 'Small multiples' draws one panel per "
              "value of the first variable. 'Automatic' groups when it fits, else panels."),
    )


def clustered_bar_schema() -> tuple[ConfigField, ...]:
    """Clustered bar charts (vertical/horizontal): support a SECOND classifying
    variable → cross-tab combos. Only these charts get it (stacked/line/radar don't)."""
    return (statistic_field(), percent_base_field(), classifying_var_field(),
            classifying_var_2_field(), xtab_layout_field(), *_common_tail())


def row_summary_fields() -> tuple[ConfigField, ...]:
    """Right-hand per-row summary column (stacked_horizontal_bar only). One value per
    bar; the picker/label fields the frontend shows depend on the chosen function.
    (spec 2026-07-07-row-summary-column)"""
    return (
        ConfigField(
            "row_summary_fn", "select", "Row summary",
            options=(("none", "None"), ("top2_sum", "Top 2 sum"),
                     ("top3_sum", "Top 3 sum"), ("sum", "Sum of selected"),
                     ("mean", "Mean"), ("net", "Net (positive − negative)")),
            default="none",
            help="Add a summary column on the right — e.g. the 4+5 'agree' share per row.",
        ),
        ConfigField("row_summary_label", "text", "Summary header", default=""),
        ConfigField("row_summary_codes", "not_answered", "Summed codes"),
        ConfigField("row_summary_pos_codes", "not_answered", "Positive codes"),
        ConfigField("row_summary_neg_codes", "not_answered", "Negative codes"),
    )


def stacked_schema(*, with_row_summary: bool = False) -> tuple[ConfigField, ...]:
    """Stacked charts: the classifying variable is OPTIONAL. With one, each bar is
    a classifier group split by the shared answer categories; without one, the
    chart is a single 100%-stacked bar of the question's answer distribution
    (the 'total'). `with_row_summary` appends the right-hand summary column fields
    (stacked HORIZONTAL bar only)."""
    return (statistic_field(), percent_base_field(), classifying_var_field(),
            # Row-summary column up front (right after the data options) so it's easy
            # to find — it's the headline feature of a stacked Likert battery.
            *(row_summary_fields() if with_row_summary else ()),
            *_common_tail(sort_stacked=True))


def single_series_schema() -> tuple[ConfigField, ...]:
    """Single-series charts (pie/doughnut/funnel): NO classifying variable."""
    return (statistic_field(), *_common_tail())


def combo_schema() -> tuple[ConfigField, ...]:
    """Combo: this question is the x-axis (bars); pick a numeric secondary
    variable for the mean-per-category line, or split by a classifying variable."""
    return (statistic_field(), percent_base_field(), combo_secondary_field(),
            classifying_var_field(), *_common_tail())
