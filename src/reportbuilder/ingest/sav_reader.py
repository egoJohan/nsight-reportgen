"""SAV reader — Task 2.1/2.2/2.3: variables, labels, value labels, measurement, missing codes, single questions."""
from __future__ import annotations

import pathlib
import re

import pandas as pd
import pyreadstat

from reportbuilder.model.question import QuestionModel, Question, Variable, ValueLabel


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or name.lower()


def _measurement(spss_measure: str) -> str:
    return "scale" if (spss_measure or "").lower() == "scale" else "categorical"


def _user_missing(ranges: list | None) -> frozenset[float]:
    codes: set[float] = set()
    for r in ranges or []:
        lo, hi = (r["lo"], r["hi"]) if isinstance(r, dict) else (r[0], r[1])
        lo, hi = float(lo), float(hi)
        if lo == hi:
            codes.add(lo)
        else:
            codes.update(float(c) for c in range(int(lo), int(hi) + 1))
    return frozenset(codes)


def read_sav(path: str | pathlib.Path) -> tuple[pd.DataFrame, QuestionModel]:
    df, meta = pyreadstat.read_sav(str(path), apply_value_formats=False, user_missing=True)
    labels = dict(meta.column_names_to_labels)
    value_labels = dict(meta.variable_value_labels)
    measures = dict(getattr(meta, "variable_measure", {}) or {})
    missing_ranges = dict(getattr(meta, "missing_ranges", {}) or {})

    variables: dict[str, Variable] = {}
    for name in df.columns:
        vls = tuple(
            ValueLabel(float(code), str(lbl))
            for code, lbl in sorted(value_labels.get(name, {}).items())
        )
        variables[name] = Variable(
            name=name,
            label=labels.get(name) or name,
            measurement=_measurement(measures.get(name, "")),
            value_labels=vls,
            missing_values=_user_missing(missing_ranges.get(name)),
        )
    questions = [
        Question(qid=_slug(name), kind="single", variables=(name,), text=variables[name].label)
        for name in df.columns
    ]
    model = QuestionModel(variables=variables, questions=questions)
    return df, model
