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
    ("data_order", "Data order"),
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


def sort_field() -> ConfigField:
    # The 'sort' widget renders both the basis (these options) and a separate
    # ascending/descending direction (descending is the default).
    return ConfigField("sort", "sort", "Sort", options=SORT_BASIS_OPTIONS, default="pct")


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
def _common_tail() -> tuple[ConfigField, ...]:
    """Knobs every data chart shares (after the classifying variable)."""
    return (
        sort_field(),
        number_format_field(),
        show_not_answered_field(),
        empty_categories_field(),
        not_answered_field(),
        category_labels_field(),
    )


def standard_schema() -> tuple[ConfigField, ...]:
    """Multi-series-capable charts: optional classifying variable."""
    return (statistic_field(), classifying_var_field(), *_common_tail())


def stacked_schema() -> tuple[ConfigField, ...]:
    """Stacked charts: the classifying variable is OPTIONAL. With one, each bar is
    a classifier group split by the shared answer categories; without one, the
    chart is a single 100%-stacked bar of the question's answer distribution
    (the 'total')."""
    return (statistic_field(), classifying_var_field(), *_common_tail())


def single_series_schema() -> tuple[ConfigField, ...]:
    """Single-series charts (pie/doughnut/funnel): NO classifying variable."""
    return (statistic_field(), *_common_tail())


def combo_schema() -> tuple[ConfigField, ...]:
    """Combo: this question is the x-axis (bars); pick a numeric secondary
    variable for the mean-per-category line, or split by a classifying variable."""
    return (statistic_field(), combo_secondary_field(),
            classifying_var_field(), *_common_tail())
