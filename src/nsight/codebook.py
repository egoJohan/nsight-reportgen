from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Codebook:
    columns: list[str]
    labels: dict[str, str]
    _value_labels: dict[str, dict[float, str]]
    measure: dict[str, str]
    missing_ranges: dict[str, list]
    var_types: dict[str, str]

    @classmethod
    def load(cls, path: Path) -> "Codebook":
        raw = json.loads(Path(path).read_text())
        value_labels = {
            var: {float(k): v for k, v in labels.items()}
            for var, labels in raw.get("value_labels", {}).items()
        }
        return cls(
            columns=raw["columns"],
            labels=raw.get("labels", {}),
            _value_labels=value_labels,
            measure=raw.get("measure", {}),
            missing_ranges=raw.get("missing_ranges", {}),
            var_types=raw.get("var_types", {}),
        )

    def label_of(self, var: str) -> str:
        return self.labels.get(var, var)

    def value_labels(self, var: str) -> dict[float, str]:
        return self._value_labels.get(var, {})

    def type_of(self, var: str) -> str:
        """Return the SPSS variable type string (e.g. 'double', 'string'), or '' if unknown."""
        return self.var_types.get(var, "")

    def find_by_label(self, substring: str) -> list[str]:
        s = substring.lower()
        return [v for v, lbl in self.labels.items() if s in (lbl or "").lower()]
