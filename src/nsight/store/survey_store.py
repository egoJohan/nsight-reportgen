from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path

# sys.path fallback: datahive is not installed as a package dependency;
# we prepend the repo directly so TabularStore is importable.
sys.path.insert(0, "/home/johan/Projects/egoiq/egohive/egohive-datahive")
from datahive.storage.tabular import FilterClause, TabularStore  # noqa: E402

import pandas as pd
import pyreadstat

from nsight.codebook import Codebook

_SURVEY_ITEM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
# allowed_groups=[] means world-readable; any scope_groups value will match.
_ABAC_OPEN = {"allowed_groups": [], "regulatory_class": "none"}
_SCOPE = {"scope_groups": ["nsight"], "scope_ceiling": "none"}

# Type substrings that identify a numeric SPSS variable type.
_NUMERIC_TYPE_TOKENS = ("double", "float", "int", "numeric")


@dataclass(frozen=True)
class IngestInfo:
    num_cases: int
    num_variables: int


class SurveyStore:
    def __init__(self, db_path: Path, codebook_path: Path) -> None:
        self._db_path = Path(db_path)
        self._codebook_path = Path(codebook_path)
        self._store = TabularStore(self._db_path)

    def ingest(self, sav_path: Path) -> IngestInfo:
        df, meta = pyreadstat.read_sav(
            str(sav_path), apply_value_formats=False, user_missing=True
        )
        columns = list(df.columns)
        self._store.create_table(item_id=_SURVEY_ITEM_ID, columns=columns)
        rows = df.where(pd.notnull(df), None).values.tolist()
        self._store.insert_rows(item_id=_SURVEY_ITEM_ID, rows=rows, abac=_ABAC_OPEN)

        var_types = (
            getattr(meta, "readstat_variable_types", None)
            or getattr(meta, "original_variable_types", {})
            or {}
        )
        codebook = {
            "columns": columns,
            "labels": dict(meta.column_names_to_labels),
            "value_labels": {
                var: {str(k): v for k, v in labels.items()}
                for var, labels in meta.variable_value_labels.items()
            },
            "measure": dict(getattr(meta, "variable_measure", {}) or {}),
            "missing_ranges": {
                k: [list(r.values()) if isinstance(r, dict) else r for r in v]
                for k, v in (getattr(meta, "missing_ranges", {}) or {}).items()
            },
            "var_types": dict(var_types),
        }
        self._codebook_path.write_text(json.dumps(codebook, ensure_ascii=False, indent=2))
        return IngestInfo(num_cases=len(df), num_variables=len(columns))

    def frame(self) -> pd.DataFrame:
        result = self._store.query(
            item_id=_SURVEY_ITEM_ID,
            filters=None,
            limit=1_000_000,
            **_SCOPE,
        )
        if not result.columns:
            return pd.DataFrame()
        df = pd.DataFrame(result.rows, columns=result.columns)

        # Load var_types from the persisted codebook to decide numeric vs string
        # by the variable's original SPSS type rather than by content inspection.
        var_types: dict[str, str] = {}
        if self._codebook_path.exists():
            try:
                raw = json.loads(self._codebook_path.read_text())
                var_types = raw.get("var_types", {})
            except Exception:
                pass

        for col in df.columns:
            col_type = var_types.get(col, "").lower()
            if col_type:
                # Recorded type: coerce only if it is a numeric SPSS type.
                if any(tok in col_type for tok in _NUMERIC_TYPE_TOKENS):
                    df[col] = pd.to_numeric(df[col], errors="coerce")
                # else: leave as string — do not coerce digit-only string vars
            else:
                # No recorded type (older DB without var_types) — fall back to
                # safe heuristic: coerce only if ALL non-null values parse as numbers.
                converted = pd.to_numeric(df[col], errors="coerce")
                if converted.notna().sum() >= df[col].notna().sum():
                    df[col] = converted
        return df

    def codebook(self) -> Codebook:
        return Codebook.load(self._codebook_path)
