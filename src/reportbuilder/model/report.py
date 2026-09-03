"""Report definition model (design §8)."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SortSpec:
    basis: str                                  # "data_order"|"pct"|"topbox_sum"|"top3_sum"|"bottom2_sum"|"bottom3_sum"|"mean"|"count" (REQ-S-01)
    topbox_codes: tuple[float, ...] = ()        # for "topbox_sum" (REQ-S-02)
    descending: bool = True


@dataclass(frozen=True)
class NumberFormat:
    mode: str = "auto"                          # "auto" (range-based) | "manual" (explicit decimals)
    pct_decimals: int = 0                       # REQ-N-01 — manual mode only
    mean_decimals: int = 1                      # REQ-N-02 — manual mode only
    count_round_up: bool = False                # REQ-N-03
    show_pct_sign: bool = True
    #: The share of the value axis below which a data label is NOT drawn.
    #:
    #: None means "whatever this chart type has always used" — 1% of the axis
    #: for a stack, 4% for a pie wedge, whose labels sit on a curve and collide
    #: sooner. There is no one right cut-off: it depends on how wide the chart
    #: is drawn and how much of the scale's tail the author is willing to lose,
    #: so it is theirs to move. 0 draws every value the chart has.
    hide_below_pct: float | None = None


@dataclass(frozen=True)
class ElementToggles:
    title: bool = True
    #: The line under the headline — the question, or whatever the author typed
    #: instead. Off is a real answer: clearing the text box means "use the
    #: question", which is the right default and left no way to say "none".
    subtitle: bool = True
    legend: bool = True
    n: bool = True
    axis_names: bool = True
    filter_var: bool = True
    data_labels: bool = True


@dataclass(frozen=True)
class ChartSpec:
    question_ref: str                           # qid (REQ-C-11)
    chart_type: str                             # canonical id (REQ-C-13)
    statistic: str                              # "pct"|"count"|"mean"|"median"|"sum" (REQ-C-15)
    classifying_var: str | None                 # segmentation -> segments + Total (REQ-C-14)
    number_format: NumberFormat
    sort: SortSpec
    template_slot: str
    elements: ElementToggles
    scatter_xy: tuple[str, str] | None = None   # scatter only (design §9a)
    classifying_var_2: str | None = None        # secondary classifier → cross-tab combos (REQ-C-14b)
    #: Which of the classifying variable's groups THIS SLIDE is computed on.
    #:
    #: Empty is every group, which is what every slide had before this existed.
    #: A property of the slide, not of the variable: a packaging study shows the
    #: whole battery through design 1 on one slide and design 2 on the next, and
    #: the pair is made by duplicating the slide and changing the tick. Naming
    #: groups narrows the RESPONDENTS, so "Total", the base and the footer's N
    #: all describe the people selected — one base for everything on the slide.
    classifying_values: tuple[str, ...] = ()
    show_not_answered: bool = False              # opt-in "Not answered" bucket for missing (REQ-D-06, MV)
    slide_title: str | None = None              # override slide title (REQ-C-24a, D-04)
    # Opaque fingerprint of the DATA slide_title was generated for (question_ref,
    # classifiers, the grouping's effect on this question, label overrides — see
    # web/src/lib/charts.ts::titleDataKey, the source of truth for what goes in).
    # Purely a round-tripped string to the backend; only the frontend computes or
    # compares it. None means either no AI title yet, or the title is hand-typed —
    # both must be left alone, so this field only ever GATES a regeneration on the
    # client, it never triggers one by its absence alone.
    slide_title_key: str | None = None
    slide_description: str | None = None        # subtitle line shown under the title (REQ-C-24a, D-04)
    footer_note: str | None = None              # override methodology footer; None = auto ("<stat> · n = N"). "{n}" expands to the base.
    # Axis titles (P-C-27, the fourth editable text property beside the title,
    # subtitle and value names). Empty = no axis title, which is how every chart
    # looked before this existed, so old reports are unchanged.
    # `elements.axis_names` still governs axis text as a whole: with it off,
    # these are not drawn even when set.
    axis_x_title: str = ""
    axis_y_title: str = ""
    show_empty_categories: bool = True           # when False, drop categories that are 0 across all segments
    not_answered_codes: tuple[float, ...] | None = None  # explicit "Not answered" code set; None = SAV-detected
    # Cross-tab percentage DIRECTION for a classified chart:
    #   "auto"       — resolve deterministically from variable roles (default)
    #   "classifier" — distribute the base var within each classifier segment (legacy)
    #   "question"   — distribute the classifier within each base category
    #   "total"      — every cell over the grand total
    percent_base: str = "auto"
    # Whether the cross-tab "Total" reference series is drawn:
    #   "auto" — hide it in a within-category % distribution (where it sits on a
    #            different denominator and can't be read alongside the segments);
    #            show it for counts/means, "% of total", and single-series charts.
    #   "on" / "off" — force it.
    show_total: str = "auto"
    category_label_overrides: tuple[tuple[str, str], ...] = ()  # (full_label, short_label) display overrides
    # Right-hand per-row summary column (stacked_horizontal_bar only). Off when
    # row_summary_fn == "none". See spec 2026-07-07-row-summary-column.
    row_summary_fn: str = "none"                 # none|top2_sum|top3_sum|bottom2_sum|bottom3_sum|sum|mean|net
    row_summary_codes: tuple[float, ...] = ()        # for "sum"
    row_summary_pos_codes: tuple[float, ...] = ()    # for "net"
    row_summary_neg_codes: tuple[float, ...] = ()    # for "net"
    row_summary_label: str = ""                       # header; "" → default_label(fn)
    options: dict[str, Any] = field(default_factory=dict)  # free-form per-chart-type options (plugin-declared config keys)
    # Per-chart identity. `question_ref` says WHICH QUESTION a chart shows and is no
    # longer unique: a comparison section adds a second slide for a question that
    # already has a total-level one. Empty on reports written before this existed;
    # the EDITOR assigns one on load. Deliberately not backfilled here: doing so
    # would make report_from_json(report_to_json(r)) != r for a code-built report
    # and break the round-trip-equality invariant the serde tests rest on.
    # (spec 2026-08-02-compare-groups-section §3)
    slide_id: str = ""
    # Unticked in Select: the slide stays in the report (keeping its content) but is
    # left OUT of the deck. Special slides have no catalog to be re-added from — the
    # row IS the chart — so unticking must not delete them, or they vanish from the
    # list with no way back.
    excluded: bool = False
    # Set on a slide generated by the "Compare groups" section, to the variable it
    # groups by. Marks the slide as NOT the question's primary slide, so the Step 1
    # question toggle leaves it alone.
    compare_group: str | None = None

    def label_override_map(self) -> dict[str, str]:
        """Return the category-label overrides as a {full_label: short_label} lookup dict."""
        return {full: short for full, short in self.category_label_overrides}


# Special (non-chart) slide types. These ride inside Report.charts as ChartSpecs
# with question_ref="" and their bullet content in options["bullets"]; the heading
# is slide_title. They are rendered as text/bullet slides, NOT data charts.
SPECIAL_SLIDE_TYPES: frozenset[str] = frozenset({
    "special_overview",
    "special_conclusion",
    "special_demographics",
    # An AUTHOR-written slide: a heading plus markdown bullets, no AI. It rides the
    # same machinery as the generated ones (bullets in options["bullets"]), and must
    # be listed here or the renderer would try to compute a data series for it.
    "special_blank",
})


def is_special_slide(spec: "ChartSpec") -> bool:
    """True for a non-chart special slide (Overview/Conclusion/Demographics/blank)."""
    return spec.chart_type in SPECIAL_SLIDE_TYPES


# Chart types whose slide is rendered as a bullet list from options["bullets"]
# rather than a data chart: the special slides plus "themes" (an open-ended
# question summarised into AI themes).
_BULLET_TYPES: frozenset[str] = SPECIAL_SLIDE_TYPES | {"themes"}


def renders_as_bullets(spec: "ChartSpec") -> bool:
    """True when the slide is text/bullets (special slides or a themes summary)
    and so has no computed data series."""
    return spec.chart_type in _BULLET_TYPES


def is_demographics_grid(spec: "ChartSpec") -> bool:
    """A multi-chart grid slide. options["charts"] = [{"question_ref","chart_type"}, …];
    each cell renders a compact chart for one question."""
    return spec.chart_type == "demographics_grid"


@dataclass(frozen=True)
class Report:
    name: str
    render_mode: str                            # "native" | "image" (per report)
    template_ref: str
    charts: tuple[ChartSpec, ...]
    # Report-specific manual grouping override {"groups": [...], "singles": [...]}
    # applied to this report's question model (auto-detection fills the gaps).
    # Default normalised so report_from_json(report_to_json(r)) == r.
    grouping: dict[str, Any] = field(
        default_factory=lambda: {"groups": [], "singles": []}
    )


_ROW_SUMMARY_DEFAULT_LABEL = {
    "top2_sum": "Top 2",
    "top3_sum": "Top 3",
    "bottom2_sum": "Bottom 2",
    "bottom3_sum": "Bottom 3",
    "sum": "Sum",
    "mean": "Keskiarvo",
    "net": "Net",
}


def default_label(fn: str) -> str:
    """Default header for a row-summary function (blank for 'none'/unknown)."""
    return _ROW_SUMMARY_DEFAULT_LABEL.get(fn, "")


def row_summary_setting(value, options: dict | None, key: str, default):
    """A row-summary setting, recovering one stranded in the free-form options bag.

    The editor writes a config value to `options` when the key is absent from the
    chart object, and a freshly created chart carried no row_summary_* keys — so
    choosing "Top 2 sum" on a new slide was saved there and silently ignored. An
    explicit top-level value always wins.

    Shared by report_from_json AND the preview endpoint: the preview builds its
    spec from the request body, not from a parsed Report, so recovering in only
    one of them leaves the on-screen chart still missing its summary column.
    """
    empty = (None, "", "none", (), [])
    if value not in empty:
        return value
    opt = (options or {}).get(key)
    if opt not in empty and opt is not None:
        return opt
    return value if value is not None else default


def report_to_json(report: Report) -> str:
    """Serialize a Report to a canonical JSON string (tuples become JSON arrays)."""
    return json.dumps(asdict(report), ensure_ascii=False, sort_keys=True)


def report_from_json(data: dict | str) -> Report:
    """Rebuild a Report from JSON (str or already-parsed dict), restoring tuples."""
    d = json.loads(data) if isinstance(data, str) else data

    def _not_answered_codes(c: dict) -> tuple[float, ...] | None:
        """Parse not_answered_codes keeping None (absent/null) distinct from () (empty)."""
        raw = c.get("not_answered_codes")
        if raw is None:
            return None
        return tuple(float(x) for x in raw)

    def _label_overrides(c: dict) -> tuple[tuple[str, str], ...]:
        """Normalize category_label_overrides from a list of [full, short] pairs or a dict."""
        raw = c.get("category_label_overrides") or ()
        if isinstance(raw, dict):
            return tuple((str(k), str(v)) for k, v in raw.items())
        return tuple((str(pair[0]), str(pair[1])) for pair in raw)

    def _rs(c: dict, key: str, default):
        return row_summary_setting(c.get(key), c.get("options"), key, default)

    def _chart(c: dict) -> ChartSpec:
        nf = c["number_format"]
        so = c["sort"]
        el = c["elements"]
        sx = c.get("scatter_xy")
        return ChartSpec(
            question_ref=c["question_ref"],
            chart_type=c["chart_type"],
            statistic=c["statistic"],
            classifying_var=c.get("classifying_var"),
            number_format=NumberFormat(
                mode=nf.get("mode", "auto"),
                pct_decimals=nf.get("pct_decimals", 0),
                mean_decimals=nf.get("mean_decimals", 1),
                count_round_up=nf.get("count_round_up", False),
                show_pct_sign=nf.get("show_pct_sign", True),
                hide_below_pct=nf.get("hide_below_pct"),
            ),
            sort=SortSpec(
                basis=so["basis"],
                topbox_codes=tuple(so.get("topbox_codes", ())),
                descending=so.get("descending", True),
            ),
            template_slot=c["template_slot"],
            elements=ElementToggles(**el),
            scatter_xy=tuple(sx) if sx is not None else None,
            classifying_var_2=c.get("classifying_var_2"),
            classifying_values=tuple(c.get("classifying_values") or ()),
            show_not_answered=c.get("show_not_answered", False),
            slide_title=c.get("slide_title"),
            slide_title_key=c.get("slide_title_key"),
            slide_description=c.get("slide_description"),
            footer_note=c.get("footer_note"),
            axis_x_title=c.get("axis_x_title", "") or "",
            axis_y_title=c.get("axis_y_title", "") or "",
            show_empty_categories=c.get("show_empty_categories", True),
            not_answered_codes=_not_answered_codes(c),
            category_label_overrides=_label_overrides(c),
            percent_base=c.get("percent_base", "auto"),
            show_total=c.get("show_total", "auto"),
            row_summary_fn=_rs(c, "row_summary_fn", "none"),
            row_summary_codes=tuple(float(x) for x in _rs(c, "row_summary_codes", ())),
            row_summary_pos_codes=tuple(float(x) for x in _rs(c, "row_summary_pos_codes", ())),
            row_summary_neg_codes=tuple(float(x) for x in _rs(c, "row_summary_neg_codes", ())),
            row_summary_label=_rs(c, "row_summary_label", ""),
            options=dict(c.get("options") or {}),
            slide_id=str(c.get("slide_id") or ""),
            excluded=bool(c.get("excluded") or False),
            compare_group=(c.get("compare_group") or None),
        )

    def _grouping(c: dict) -> dict:
        g = c.get("grouping") or {}
        return {
            "groups": [dict(x) for x in g.get("groups", [])],
            "singles": list(g.get("singles", [])),
        }

    return Report(
        name=d["name"],
        render_mode=d["render_mode"],
        template_ref=d["template_ref"],
        charts=tuple(_chart(c) for c in d["charts"]),
        grouping=_grouping(d),
    )
