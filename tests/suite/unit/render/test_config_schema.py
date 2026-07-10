"""Unit tests for reportbuilder.render.config_schema — ConfigField.to_dict()
and the composed per-family schemas (pure, declarative UI contract)."""
from __future__ import annotations

from reportbuilder.render.config_schema import (
    ConfigField,
    STATISTIC_OPTIONS,
    SORT_BASIS_OPTIONS,
    statistic_field,
    classifying_var_field,
    sort_field,
    number_format_field,
    show_not_answered_field,
    empty_categories_field,
    not_answered_field,
    category_labels_field,
    note_field,
    combo_secondary_field,
    standard_schema,
    stacked_schema,
    single_series_schema,
    combo_schema,
)


def _keys(schema):
    return [f.key for f in schema]


# ---- ConfigField.to_dict ---------------------------------------------------

def test_to_dict_minimal_emits_only_key_widget_label():
    d = ConfigField("k", "select").to_dict()
    assert d == {"key": "k", "widget": "select", "label": ""}


def test_to_dict_omits_help_when_none():
    assert "help" not in ConfigField("k", "select").to_dict()


def test_to_dict_omits_options_when_empty():
    assert "options" not in ConfigField("k", "select").to_dict()


def test_to_dict_omits_default_when_none():
    assert "default" not in ConfigField("k", "select").to_dict()


def test_to_dict_omits_required_when_false():
    assert "required" not in ConfigField("k", "select").to_dict()


def test_to_dict_full_field_emits_all_keys():
    f = ConfigField(
        key="statistic", widget="select", label="Statistic",
        help="pick one", options=(("pct", "Percentage"), ("count", "Count")),
        default="pct", required=True,
    )
    d = f.to_dict()
    assert d == {
        "key": "statistic",
        "widget": "select",
        "label": "Statistic",
        "help": "pick one",
        "options": [{"value": "pct", "label": "Percentage"},
                    {"value": "count", "label": "Count"}],
        "default": "pct",
        "required": True,
    }


def test_to_dict_false_default_is_kept():
    # default is `False` (not None) so it must be emitted.
    d = show_not_answered_field().to_dict()
    assert d["default"] is False


def test_to_dict_true_default_is_kept():
    assert empty_categories_field().to_dict()["default"] is True


# ---- Individual field factories -------------------------------------------

def test_statistic_field():
    f = statistic_field()
    assert f.key == "statistic"
    assert f.widget == "select"
    assert f.default == "pct"
    assert f.options == STATISTIC_OPTIONS
    d = f.to_dict()
    assert d["options"][0] == {"value": "pct", "label": "Percentage"}


def test_sort_field():
    f = sort_field()
    assert f.key == "sort"
    assert f.widget == "sort"
    assert f.default == "pct"
    assert f.options == SORT_BASIS_OPTIONS


def test_number_format_field():
    f = number_format_field()
    assert (f.key, f.widget, f.default) == ("number_format", "number_format", "auto")


def test_not_answered_field():
    f = not_answered_field()
    assert (f.key, f.widget) == ("not_answered_codes", "not_answered")


def test_category_labels_field():
    f = category_labels_field()
    assert (f.key, f.widget) == ("category_label_overrides", "category_labels")


def test_note_field_carries_text_in_help():
    f = note_field("hello there")
    assert f.key == "note" and f.widget == "note" and f.label == ""
    assert f.help == "hello there"


def test_combo_secondary_field():
    f = combo_secondary_field()
    assert f.key == "combo_secondary"
    assert f.widget == "numeric_variable"


# ---- classifying_var_field: optional vs required --------------------------

def test_classifying_var_field_default_is_optional():
    f = classifying_var_field()
    assert f.key == "classifying_var"
    assert f.widget == "variable"
    assert f.required is False
    assert "Break the chart down" in f.help


def test_classifying_var_field_required_variant():
    f = classifying_var_field(required=True)
    assert f.required is True
    assert "Required" in f.help
    assert f.to_dict()["required"] is True


# ---- Composed schemas: field sets per family ------------------------------

def test_standard_schema_field_set():
    keys = _keys(standard_schema())
    # percent_base sits right after statistic (renders on the "Statistic" row);
    # show_total (the "Total column" control) follows it.
    assert keys == [
        "statistic", "percent_base", "show_total", "classifying_var", "sort",
        "number_format", "show_not_answered", "show_empty_categories",
        "not_answered_codes", "category_label_overrides",
    ]


def test_standard_schema_classifying_var_is_optional():
    cv = next(f for f in standard_schema() if f.key == "classifying_var")
    assert cv.required is False


def test_stacked_schema_classifying_var_is_optional():
    # Total-only stacked bars are valid, so the classifying variable is optional.
    cv = next(f for f in stacked_schema() if f.key == "classifying_var")
    assert cv.required is False


def test_stacked_schema_same_field_set_as_standard():
    # Stacked bars never draw a "Total" bar (bars exclude Total), so stacked omits the
    # show_total control; otherwise its field set matches standard.
    assert _keys(stacked_schema()) == [
        k for k in _keys(standard_schema()) if k != "show_total"
    ]


def test_single_series_schema_omits_classifying_var():
    keys = _keys(single_series_schema())
    assert "classifying_var" not in keys
    assert keys == [
        "statistic", "sort", "number_format", "show_not_answered",
        "show_empty_categories", "not_answered_codes", "category_label_overrides",
    ]


def test_combo_schema_has_combo_secondary_and_classifying_var():
    keys = _keys(combo_schema())
    assert "combo_secondary" in keys
    assert "classifying_var" in keys
    # combo_secondary comes right after statistic, before classifying_var.
    assert keys.index("combo_secondary") < keys.index("classifying_var")


def test_combo_schema_classifying_var_is_optional():
    cv = next(f for f in combo_schema() if f.key == "classifying_var")
    assert cv.required is False


def test_stacked_horizontal_row_summary_fields():
    from reportbuilder.render.config_schema import stacked_schema
    hks = [f.key for f in stacked_schema(with_row_summary=True)]
    for k in ("row_summary_fn", "row_summary_label", "row_summary_codes",
              "row_summary_pos_codes", "row_summary_neg_codes"):
        assert k in hks
    fn = next(f for f in stacked_schema(with_row_summary=True)
              if f.key == "row_summary_fn")
    assert fn.widget == "select"
    assert {v for v, _ in fn.options} == {
        "none", "top2_sum", "top3_sum", "sum", "mean", "net"}
    # the default stacked schema (used by vertical) does NOT include it
    assert "row_summary_fn" not in [f.key for f in stacked_schema()]
