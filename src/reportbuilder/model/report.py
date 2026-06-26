"""Report definition model (design §8)."""
from __future__ import annotations
import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class SortSpec:
    basis: str                                  # "data_order"|"pct"|"topbox_sum"|"mean"|"count" (REQ-S-01)
    topbox_codes: tuple[float, ...] = ()        # for "topbox_sum" (REQ-S-02)
    descending: bool = True


@dataclass(frozen=True)
class NumberFormat:
    mode: str = "auto"                          # "auto" (range-based) | "manual" (explicit decimals)
    pct_decimals: int = 0                       # REQ-N-01 — manual mode only
    mean_decimals: int = 1                      # REQ-N-02 — manual mode only
    count_round_up: bool = False                # REQ-N-03
    show_pct_sign: bool = True


@dataclass(frozen=True)
class ElementToggles:
    title: bool = True
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
    show_not_answered: bool = False              # opt-in "Not answered" bucket for missing (REQ-D-06, MV)
    slide_title: str | None = None              # override slide title (REQ-C-24a, D-04)
    slide_description: str | None = None        # subtitle line shown under the title (REQ-C-24a, D-04)


@dataclass(frozen=True)
class Report:
    name: str
    render_mode: str                            # "native" | "image" (per report)
    template_ref: str
    charts: tuple[ChartSpec, ...]


def report_to_json(report: Report) -> str:
    """Serialize a Report to a canonical JSON string (tuples become JSON arrays)."""
    return json.dumps(asdict(report), ensure_ascii=False, sort_keys=True)


def report_from_json(data: dict | str) -> Report:
    """Rebuild a Report from JSON (str or already-parsed dict), restoring tuples."""
    d = json.loads(data) if isinstance(data, str) else data

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
            ),
            sort=SortSpec(
                basis=so["basis"],
                topbox_codes=tuple(so.get("topbox_codes", ())),
                descending=so.get("descending", True),
            ),
            template_slot=c["template_slot"],
            elements=ElementToggles(**el),
            scatter_xy=tuple(sx) if sx is not None else None,
            show_not_answered=c.get("show_not_answered", False),
            slide_title=c.get("slide_title"),
            slide_description=c.get("slide_description"),
        )

    return Report(
        name=d["name"],
        render_mode=d["render_mode"],
        template_ref=d["template_ref"],
        charts=tuple(_chart(c) for c in d["charts"]),
    )
