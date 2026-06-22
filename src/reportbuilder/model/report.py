"""Report definition model (design §8)."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class SortSpec:
    basis: str                                  # "data_order"|"pct"|"topbox_sum"|"mean"|"count" (REQ-S-01)
    topbox_codes: tuple[float, ...] = ()        # for "topbox_sum" (REQ-S-02)
    descending: bool = True


@dataclass(frozen=True)
class NumberFormat:
    pct_decimals: int = 0                       # REQ-N-01
    mean_decimals: int = 1                      # REQ-N-02
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
    statistic: str                              # "pct"|"count"|"mean" (REQ-C-15)
    classifying_var: str | None                 # segmentation -> segments + Total (REQ-C-14)
    number_format: NumberFormat
    sort: SortSpec
    template_slot: str
    elements: ElementToggles
    scatter_xy: tuple[str, str] | None = None   # scatter only (design §9a)


@dataclass(frozen=True)
class Report:
    name: str
    render_mode: str                            # "native" | "image" (per report)
    template_ref: str
    charts: tuple[ChartSpec, ...]
