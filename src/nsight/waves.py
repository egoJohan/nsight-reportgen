from __future__ import annotations

import json
from pathlib import Path


class WaveHistory:
    """Prior-wave numbers extracted from the original deck. Key: wave/metric/key -> int pct."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._data = json.loads(self._path.read_text()) if self._path.exists() else {}

    def set(self, wave: str, metric: str, key: str, value: int) -> None:
        self._data.setdefault(wave, {}).setdefault(metric, {})[key] = value
        self._path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2))

    def get(self, wave: str, metric: str, key: str) -> int | None:
        return self._data.get(wave, {}).get(metric, {}).get(key)

    def delta(self, *, current: int, prior_wave: str, metric: str, key: str) -> int | None:
        prior = self.get(prior_wave, metric, key)
        return None if prior is None else current - prior
