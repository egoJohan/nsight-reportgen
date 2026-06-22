from __future__ import annotations

from typing import Callable

import pandas as pd

# Real Attendo variable bindings (Task M-1).
#
# Experience is a multi-select grid (var11O19..O22, coded 0=Unchecked / 1=Checked):
#   var11O19  "...henkilökohtaista kokemusta ... asiakkaana"   (personal, as client)
#   var11O20  "...kokemusta ... asiakkaan läheisenä"           (as a client's relative)
#   var11O21  "...työskentelen / olen työskennellyt ..."        (works/has worked in care)
#   var11O22  "Ei, minulla ei ole kokemusta hoivapalveluista"   (no experience)
# Recommenders ("suosittelijat") = chose Attendo in the would-choose grid (var158O706).
#
# IMPORTANT: these are the closest real-variable bindings, but they do NOT
# reproduce the deck's segment bases (deck: experience n=608, no-experience n=245,
# recommenders n=234, professionals n=257). See attendo_bindings.DECK_SEGMENT_BASES
# and the M-1 note there — the deck's segment definitions rely on survey routing /
# derived population not recoverable from this .sav, so segment-split charts are NOT
# golden-tested. Bindings are kept for downstream "kaikki" use and documentation.
DEFAULTS = {
    "exp_client_var": "var11O19",
    "exp_relative_var": "var11O20",
    "exp_work_var": "var11O21",
    "exp_none_var": "var11O22",
    "recommend_attendo_var": "var158O706",
}


def _num(frame: pd.DataFrame, var: str) -> pd.Series:
    return pd.to_numeric(frame[var], errors="coerce")


def _all(frame: pd.DataFrame, v: dict) -> pd.Series:
    return pd.Series([True] * len(frame), index=frame.index)


def _experienced(frame: pd.DataFrame, v: dict) -> pd.Series:
    return (
        (_num(frame, v["exp_client_var"]) == 1.0)
        | (_num(frame, v["exp_relative_var"]) == 1.0)
        | (_num(frame, v["exp_work_var"]) == 1.0)
    )


def _inexperienced(frame: pd.DataFrame, v: dict) -> pd.Series:
    return _num(frame, v["exp_none_var"]) == 1.0


def _professionals(frame: pd.DataFrame, v: dict) -> pd.Series:
    return _num(frame, v["exp_work_var"]) == 1.0


def _recommenders(frame: pd.DataFrame, v: dict) -> pd.Series:
    return _num(frame, v["recommend_attendo_var"]) == 1.0


SEGMENTS: dict[str, Callable[[pd.DataFrame, dict], pd.Series]] = {
    "kaikki": _all,
    "kokemusta_omaavat": _experienced,
    "kokemattomat": _inexperienced,
    "ammattilaiset": _professionals,
    "suosittelijat": _recommenders,
}


def segment_mask(name: str, frame: pd.DataFrame, var_overrides: dict | None = None) -> pd.Series:
    if name not in SEGMENTS:
        raise KeyError(f"unknown segment: {name}")
    v = {**DEFAULTS, **(var_overrides or {})}
    return SEGMENTS[name](frame, v)
