"""SAV reader — Task 2.1: variables, labels, value labels, measurement."""
from __future__ import annotations

import pathlib

import pandas as pd
import pyreadstat

from reportbuilder.model.question import QuestionModel, Variable, ValueLabel


def _measurement(spss_measure: str) -> str:
    return "scale" if (spss_measure or "").lower() == "scale" else "categorical"


def read_sav(path: str | pathlib.Path) -> tuple[pd.DataFrame, QuestionModel]:
    df, meta = pyreadstat.read_sav(str(path), apply_value_formats=False, user_missing=True)
    labels = dict(meta.column_names_to_labels)
    value_labels = dict(meta.variable_value_labels)
    measures = dict(getattr(meta, "variable_measure", {}) or {})

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
            missing_values=frozenset(),   # populated in Task 2.2
        )
    model = QuestionModel(variables=variables, questions=[])
    return df, model
