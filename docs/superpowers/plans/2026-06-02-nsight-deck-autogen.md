# nSight deck auto-generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Regenerate the Attendo Nov 2025 brand-tracking deck from its SPSS file, driven by a natural-language brief, rendered into the original deck used as a fixed template, and scored for fidelity against the original.

**Architecture:** Deterministic Python engine computes every number (shares, cross-tabs, wave deltas, open-ended word lists) in-process from respondent rows read out of DataHive's `TabularStore` (DuckDB); a render layer fills the original `.pptx` in place across three carriers (native charts, data tables, text boxes); a Claude Agent SDK workflow reads the brief, calls the deterministic tools, and writes Finnish narrative; a fidelity harness compares generated vs. original; a FastAPI + light web UI drives it. Numbers are never produced by the LLM.

**Tech Stack:** Python 3.11+, `uv`, `pyreadstat` (SPSS read), DataHive `TabularStore` (DuckDB) as a path dependency, `pandas` (in-process aggregation), `python-pptx` (render + extraction), `claude-agent-sdk` (orchestration), `FastAPI` + `uvicorn` (web app), `pytest` (tests).

---

## Conventions & ground rules

- **Spec:** `docs/superpowers/specs/2026-06-02-nsight-deck-autogen-design.md`. Read it before starting.
- **Git:** The repo owner (Johan) manages version control. Treat every `git commit` step as a checkpoint: stop, report what changed, and let the owner commit. Do **not** run git write commands yourself.
- **TDD:** Every task writes a failing test first, watches it fail, implements minimally, watches it pass. Run `uv run pytest` from the project root `/home/johan/Projects/nsight/proto`.
- **Determinism:** No LLM call ever returns a number that lands in a chart/table. The agent only routes to tools and writes prose.
- **Fidelity tolerance:** percentages compared after rounding to whole percent (the deck's convention).
- **Decisions deferred to runtime (resolve as you hit them, record the answer in the spec's §10):** weighting policy (likely unweighted — confirm against a known chart), exact segment predicates, original open-ended coding scheme.

## File structure (created across the plan)

```
proto/
  pyproject.toml                      # uv project, deps, pytest config
  briefs/attendo.md                   # the natural-language brief (the template/spec)
  src/nsight/
    __init__.py
    config.py                         # paths: input dir, work dir, template, db
    store/
      __init__.py
      survey_store.py                 # SurveyStore: ingest .sav -> DuckDB + codebook.json; frame(); codebook()
    codebook.py                       # Codebook: var lookup by name/label, value labels, missing handling
    segments.py                       # SEGMENTS registry: name -> predicate(frame)->bool mask
    tabulate.py                       # share, crosstab, top_of_mind, perception_split, wave_delta
    coding.py                         # open-ended coding -> ranked TOP-N word lists
    waves.py                          # WaveHistory: load/store historical wave numbers + codings
    brief.py                          # Brief model + parser (YAML front-matter blocks -> SlideJob)
    render/
      __init__.py
      template.py                     # Template: open pptx, index shapes by (slide_idx, shape_name)
      fill_chart.py                   # replace native chart data
      fill_table.py                   # write table cells
      fill_text.py                    # write text-box runs
      renderer.py                     # apply a SlideFill to the template, save out
    agent/
      __init__.py
      tools.py                        # claude-agent-sdk @tool wrappers over the engine
      workflow.py                     # generate_deck(): brief -> per-slide tool calls -> render
    fidelity/
      __init__.py
      extract.py                      # pptx -> structured {charts, tables, texts}
      compare.py                      # score generated vs original
    webapp/
      __init__.py
      app.py                          # FastAPI: list inputs, run, stream log, download, report
      static/index.html               # minimal UI
  tests/
    conftest.py                       # fixtures: tiny synthetic frame, sample template path
    test_survey_store.py
    test_codebook.py
    test_segments.py
    test_tabulate.py
    test_coding.py
    test_brief.py
    test_render_chart.py
    test_render_table.py
    test_render_text.py
    test_fidelity_extract.py
    test_fidelity_compare.py
    test_golden_attendo.py            # integration: real .sav vs real deck within tolerance
    test_webapp.py
  work/                               # runtime artifacts (gitignored): survey.duckdb, codebook.json, generated.pptx
```

---

## Milestone 0 — Project scaffold & data plane

### Task 0.1: Initialize the uv project

**Files:**
- Create: `pyproject.toml`
- Create: `src/nsight/__init__.py`
- Create: `src/nsight/config.py`
- Create: `.gitignore`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "nsight"
version = "0.1.0"
description = "Automated nSight market-research deck generation"
requires-python = ">=3.11"
dependencies = [
    "pyreadstat>=1.2",
    "pandas>=2.2",
    "python-pptx>=1.0",
    "claude-agent-sdk>=0.1",
    "fastapi>=0.115",
    "uvicorn>=0.30",
    "python-multipart>=0.0.9",
    "pyyaml>=6.0",
    "datahive",
]

[project.optional-dependencies]
dev = ["pytest>=8.0", "pytest-asyncio>=0.24", "httpx>=0.27"]

[tool.uv.sources]
datahive = { path = "../../egoiq/egohive/egohive-datahive", editable = true }

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/nsight"]

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create package init and config**

`src/nsight/__init__.py`:
```python
"""Automated nSight market-research deck generation."""
```

`src/nsight/config.py`:
```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "input"
WORK_DIR = ROOT / "work"
BRIEFS_DIR = ROOT / "briefs"

ATTENDO_SAV = INPUT_DIR / "spss AttendoSuomi-Brandiseuranta_112025.sav"
ATTENDO_TEMPLATE = INPUT_DIR / "Attendo Bränditutkimus Marraskuu 2025.pptx"

SURVEY_DB = WORK_DIR / "survey.duckdb"
CODEBOOK_JSON = WORK_DIR / "codebook.json"
WAVES_JSON = WORK_DIR / "waves.json"
GENERATED_PPTX = WORK_DIR / "attendo_generated.pptx"

WORK_DIR.mkdir(parents=True, exist_ok=True)
```

`.gitignore`:
```
work/
.venv/
__pycache__/
*.pyc
.pytest_cache/
```

- [ ] **Step 3: Sync dependencies and verify the DataHive import works**

Run: `cd /home/johan/Projects/nsight/proto && uv sync --extra dev`
Then: `uv run python -c "from datahive.storage.tabular import TabularStore, FilterClause; import pptx, pyreadstat, pandas; print('deps OK')"`
Expected: prints `deps OK`. If the `datahive` path install pulls heavy deps that fail, fall back: drop `datahive` from `dependencies`, and instead add the repo to the path inside `survey_store.py` via `sys.path.insert(0, str(Path('../../egoiq/egohive/egohive-datahive')))` before importing `TabularStore`. Record whichever path you took.

- [ ] **Step 4: Commit** (checkpoint — owner commits)

```bash
git add pyproject.toml src/nsight/__init__.py src/nsight/config.py .gitignore
git commit -m "chore: scaffold nsight prototype project"
```

---

### Task 0.2: SurveyStore — ingest the .sav into DuckDB + codebook

**Files:**
- Create: `src/nsight/store/__init__.py` (empty)
- Create: `src/nsight/store/survey_store.py`
- Create: `tests/conftest.py`
- Test: `tests/test_survey_store.py`

- [ ] **Step 1: Write `tests/conftest.py` with a tiny synthetic SPSS frame fixture**

```python
import uuid
from pathlib import Path

import pandas as pd
import pyreadstat
import pytest


@pytest.fixture
def tiny_sav(tmp_path: Path) -> Path:
    """A 6-respondent survey: one categorical awareness var, one segment var, one open-ended var."""
    df = pd.DataFrame(
        {
            "aware_attendo": [1, 1, 0, 1, 0, 1],      # 1=knows, 0=doesn't
            "experience": [1, 2, 1, 2, 1, 2],          # 1=experienced, 2=inexperienced
            "image_word": ["kallis", "Kallis ", "luotettava", "kallis", "hyvä", "luotettava"],
        }
    )
    out = tmp_path / "tiny.sav"
    pyreadstat.write_sav(
        df,
        str(out),
        column_labels=["Tunnetko Attendo", "Kokemus", "Kuvaile Attendoa"],
        variable_value_labels={
            "aware_attendo": {1.0: "Kyllä", 0.0: "Ei"},
            "experience": {1.0: "Kokemusta", 2.0: "Ei kokemusta"},
        },
    )
    return out
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_survey_store.py
from nsight.store.survey_store import SurveyStore


def test_ingest_then_frame_roundtrips_rows(tiny_sav, tmp_path):
    store = SurveyStore(db_path=tmp_path / "s.duckdb", codebook_path=tmp_path / "cb.json")
    info = store.ingest(tiny_sav)
    assert info.num_cases == 6
    assert info.num_variables == 3

    frame = store.frame()
    assert len(frame) == 6
    assert set(frame.columns) >= {"aware_attendo", "experience", "image_word"}
    # raw codes preserved (not value-formatted)
    assert sorted(frame["aware_attendo"].astype(float).unique().tolist()) == [0.0, 1.0]


def test_codebook_persisted(tiny_sav, tmp_path):
    store = SurveyStore(db_path=tmp_path / "s.duckdb", codebook_path=tmp_path / "cb.json")
    store.ingest(tiny_sav)
    cb = store.codebook()
    assert cb.label_of("aware_attendo") == "Tunnetko Attendo"
    assert cb.value_labels("aware_attendo")[1.0] == "Kyllä"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_survey_store.py -v`
Expected: FAIL with `ModuleNotFoundError: nsight.store.survey_store`.

- [ ] **Step 4: Implement `survey_store.py`**

```python
# src/nsight/store/survey_store.py
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pyreadstat

from datahive.storage.tabular import FilterClause, TabularStore
from nsight.codebook import Codebook

# Deterministic table identity so re-opening the same DB finds the same table.
_SURVEY_ITEM_ID = uuid.UUID("00000000-0000-0000-0000-0000000000a1")
_ABAC_OPEN = {"allowed_groups": [], "regulatory_class": "none"}
_SCOPE = {"scope_groups": ["nsight"], "scope_ceiling": "none"}


@dataclass(frozen=True)
class IngestInfo:
    num_cases: int
    num_variables: int


class SurveyStore:
    """Ingest a .sav into DataHive's TabularStore (DuckDB) and persist a codebook JSON.

    The respondent rows live in DuckDB; the codebook (labels, value labels, missing
    ranges, measure) is persisted as JSON alongside. Aggregation happens in-process
    via frame() — TabularStore has no GROUP BY.
    """

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
        }
        self._codebook_path.write_text(json.dumps(codebook, ensure_ascii=False, indent=2))
        return IngestInfo(num_cases=len(df), num_variables=len(columns))

    def frame(self) -> pd.DataFrame:
        """Return all respondent rows as a DataFrame (numeric columns coerced)."""
        result = self._store.query(
            item_id=_SURVEY_ITEM_ID,
            filters=None,
            limit=1_000_000,
            **_SCOPE,
        )
        df = pd.DataFrame(result.rows, columns=result.columns)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="ignore")
        return df

    def codebook(self) -> Codebook:
        return Codebook.load(self._codebook_path)
```

- [ ] **Step 5: Run test — expect import error for `nsight.codebook`** (built next task). To unblock this task in isolation, temporarily run only after Task 0.3 lands, OR implement `Codebook` first. **Reorder note:** implement Task 0.3 before re-running Step 6.

- [ ] **Step 6: After Codebook exists, run tests to verify they pass**

Run: `uv run pytest tests/test_survey_store.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit** (checkpoint)

```bash
git add src/nsight/store tests/test_survey_store.py tests/conftest.py
git commit -m "feat: SurveyStore ingests .sav into DuckDB + codebook"
```

---

### Task 0.3: Codebook lookup

**Files:**
- Create: `src/nsight/codebook.py`
- Test: `tests/test_codebook.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_codebook.py
import json
from nsight.codebook import Codebook


def _cb(tmp_path):
    p = tmp_path / "cb.json"
    p.write_text(json.dumps({
        "columns": ["aware_attendo", "q5"],
        "labels": {"aware_attendo": "Tunnetko Attendo", "q5": "Yleinen käsitys"},
        "value_labels": {"aware_attendo": {"1.0": "Kyllä", "0.0": "Ei"}},
        "measure": {"aware_attendo": "nominal"},
        "missing_ranges": {},
    }, ensure_ascii=False))
    return Codebook.load(p)


def test_label_and_value_labels(tmp_path):
    cb = _cb(tmp_path)
    assert cb.label_of("aware_attendo") == "Tunnetko Attendo"
    assert cb.value_labels("aware_attendo")[1.0] == "Kyllä"


def test_find_by_label_substring(tmp_path):
    cb = _cb(tmp_path)
    assert cb.find_by_label("yleinen käsitys") == ["q5"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_codebook.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `codebook.py`**

```python
# src/nsight/codebook.py
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
        )

    def label_of(self, var: str) -> str:
        return self.labels.get(var, var)

    def value_labels(self, var: str) -> dict[float, str]:
        return self._value_labels.get(var, {})

    def find_by_label(self, substring: str) -> list[str]:
        s = substring.lower()
        return [v for v, lbl in self.labels.items() if s in (lbl or "").lower()]
```

- [ ] **Step 4: Run tests (codebook + survey_store) to verify they pass**

Run: `uv run pytest tests/test_codebook.py tests/test_survey_store.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/codebook.py tests/test_codebook.py
git commit -m "feat: Codebook lookup"
```

---

### Task 0.4: Ingest the real Attendo .sav (smoke check)

**Files:**
- Test: `tests/test_survey_store.py` (add one integration test, marked)

- [ ] **Step 1: Add a real-data smoke test**

```python
# append to tests/test_survey_store.py
import pytest
from nsight import config
from nsight.store.survey_store import SurveyStore


@pytest.mark.integration
def test_real_attendo_ingest():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo .sav not present")
    store = SurveyStore(db_path=config.SURVEY_DB, codebook_path=config.CODEBOOK_JSON)
    info = store.ingest(config.ATTENDO_SAV)
    assert info.num_cases == 1001
    assert info.num_variables == 229
    frame = store.frame()
    assert len(frame) == 1001
```

- [ ] **Step 2: Register the `integration` marker** — add to `pyproject.toml` under `[tool.pytest.ini_options]`:

```toml
markers = ["integration: touches the real Attendo files"]
```

- [ ] **Step 3: Run the integration test**

Run: `uv run pytest tests/test_survey_store.py -v -m integration`
Expected: PASS — confirms 1001 cases / 229 vars and that `frame()` reads all rows from DuckDB. This materializes `work/survey.duckdb` and `work/codebook.json` used by later golden tests.

- [ ] **Step 4: Commit** (checkpoint)

```bash
git add tests/test_survey_store.py pyproject.toml
git commit -m "test: real Attendo ingest smoke check"
```

---

## Milestone 1 — Segments & categorical tabulation (the data core)

### Task 1.1: Segment dictionary

**Files:**
- Create: `src/nsight/segments.py`
- Test: `tests/test_segments.py`

The deck's segments: `kaikki` (all), `kokemusta_omaavat` (experienced), `kokemattomat` (inexperienced), `ammattilaiset` (professionals), `suosittelijat` (recommenders). Each is a predicate over the frame returning a boolean mask. **The exact variable for each segment is unknown until you read the codebook** — Step 3 defines them against the synthetic fixture; Task 1.4 binds the real variables against the codebook and validates n= against the deck.

- [ ] **Step 1: Write the failing test (synthetic semantics)**

```python
# tests/test_segments.py
import pandas as pd
from nsight.segments import segment_mask, SEGMENTS


def test_all_segment_selects_everyone():
    frame = pd.DataFrame({"experience": [1, 2, 1]})
    mask = segment_mask("kaikki", frame)
    assert mask.tolist() == [True, True, True]


def test_experienced_segment_predicate():
    frame = pd.DataFrame({"experience": [1, 2, 1, 2]})
    # synthetic mapping: experience==1 -> experienced
    mask = segment_mask("kokemusta_omaavat", frame, var_overrides={"experience_var": "experience"})
    assert mask.tolist() == [True, False, True, False]


def test_unknown_segment_raises():
    frame = pd.DataFrame({"x": [1]})
    try:
        segment_mask("nope", frame)
        assert False, "expected KeyError"
    except KeyError:
        pass
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_segments.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `segments.py`**

```python
# src/nsight/segments.py
from __future__ import annotations

from typing import Callable

import pandas as pd

# Default variable bindings; overridden per real survey in Task 1.4.
DEFAULTS = {"experience_var": "experience"}


def _all(frame: pd.DataFrame, v: dict) -> pd.Series:
    return pd.Series([True] * len(frame), index=frame.index)


def _experienced(frame: pd.DataFrame, v: dict) -> pd.Series:
    return frame[v["experience_var"]].astype(float) == 1.0


def _inexperienced(frame: pd.DataFrame, v: dict) -> pd.Series:
    return frame[v["experience_var"]].astype(float) == 2.0


SEGMENTS: dict[str, Callable[[pd.DataFrame, dict], pd.Series]] = {
    "kaikki": _all,
    "kokemusta_omaavat": _experienced,
    "kokemattomat": _inexperienced,
    # ammattilaiset / suosittelijat added in Task 1.4 once their variables are known
}


def segment_mask(name: str, frame: pd.DataFrame, var_overrides: dict | None = None) -> pd.Series:
    if name not in SEGMENTS:
        raise KeyError(f"unknown segment: {name}")
    v = {**DEFAULTS, **(var_overrides or {})}
    return SEGMENTS[name](frame, v)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_segments.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/segments.py tests/test_segments.py
git commit -m "feat: segment dictionary"
```

---

### Task 1.2: Categorical tabulation tools

**Files:**
- Create: `src/nsight/tabulate.py`
- Test: `tests/test_tabulate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_tabulate.py
import pandas as pd
from nsight.tabulate import share, perception_split


def test_share_of_value_unweighted():
    frame = pd.DataFrame({"aware": [1, 1, 0, 1, 0, 0]})  # 3/6 = 50%
    res = share(frame, var="aware", positive_values=[1.0])
    assert res.pct == 50.0
    assert res.n == 6


def test_share_excludes_missing():
    frame = pd.DataFrame({"aware": [1, 1, None, 1, None]})  # 3 valid, all positive
    res = share(frame, var="aware", positive_values=[1.0])
    assert res.pct == 100.0
    assert res.n == 3


def test_share_weighted():
    frame = pd.DataFrame({"aware": [1, 0], "w": [3.0, 1.0]})  # weighted: 3/(3+1)=75%
    res = share(frame, var="aware", positive_values=[1.0], weight="w")
    assert res.pct == 75.0


def test_perception_split_three_way():
    # codes: 1,2=positive 3=neutral 4,5=negative
    frame = pd.DataFrame({"op": [1, 2, 3, 4, 5, 1]})
    res = perception_split(frame, var="op", positive=[1, 2], neutral=[3], negative=[4, 5])
    assert res.positive == 50.0   # 3/6
    assert res.neutral == round(100 / 6, 0)
    assert res.negative == round(200 / 6, 0)
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_tabulate.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `tabulate.py`**

```python
# src/nsight/tabulate.py
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class ShareResult:
    pct: float          # rounded to whole percent
    n: int              # valid (non-missing) base
    raw: float          # unrounded proportion * 100


@dataclass(frozen=True)
class PerceptionResult:
    positive: float
    neutral: float
    negative: float
    n: int


def _valid(frame: pd.DataFrame, var: str, weight: str | None):
    s = pd.to_numeric(frame[var], errors="coerce")
    valid = s.notna()
    w = pd.to_numeric(frame[weight], errors="coerce") if weight else pd.Series(1.0, index=frame.index)
    return s[valid], w[valid]


def share(frame: pd.DataFrame, *, var: str, positive_values: list[float],
          weight: str | None = None) -> ShareResult:
    s, w = _valid(frame, var, weight)
    total = w.sum()
    hit = w[s.isin(positive_values)].sum()
    raw = (hit / total * 100.0) if total else 0.0
    return ShareResult(pct=round(raw), n=int(s.shape[0]), raw=raw)


def perception_split(frame: pd.DataFrame, *, var: str, positive: list[float],
                     neutral: list[float], negative: list[float],
                     weight: str | None = None) -> PerceptionResult:
    s, w = _valid(frame, var, weight)
    total = w.sum()
    def pct(codes): return round(w[s.isin(codes)].sum() / total * 100.0) if total else 0.0
    return PerceptionResult(positive=pct(positive), neutral=pct(neutral),
                            negative=pct(negative), n=int(s.shape[0]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_tabulate.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/tabulate.py tests/test_tabulate.py
git commit -m "feat: categorical tabulation (share, perception_split)"
```

---

### Task 1.3: Awareness aggregation across brands + top-of-mind

**Files:**
- Modify: `src/nsight/tabulate.py` (add `awareness_by_brand`, `top_of_mind`)
- Test: `tests/test_tabulate.py` (add tests)

- [ ] **Step 1: Add failing tests**

```python
# append to tests/test_tabulate.py
from nsight.tabulate import awareness_by_brand, top_of_mind


def test_awareness_by_brand_multi_columns():
    # one yes/no column per brand
    frame = pd.DataFrame({
        "aw_attendo": [1, 1, 1, 0],   # 75%
        "aw_esperi":  [1, 0, 0, 0],   # 25%
    })
    res = awareness_by_brand(frame, brand_vars={"Attendo": "aw_attendo", "Esperi": "aw_esperi"})
    assert res["Attendo"].pct == 75.0
    assert res["Esperi"].pct == 25.0


def test_top_of_mind_first_mention():
    # first-mention string column; case/space-insensitive match
    frame = pd.DataFrame({"first": ["Attendo", "attendo ", "Esperi", "Attendo"]})
    res = top_of_mind(frame, first_mention_var="first", brand="Attendo")
    assert res.pct == 75.0  # 3/4
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `uv run pytest tests/test_tabulate.py -v -k "awareness or top_of_mind"`
Expected: FAIL (ImportError for the new names).

- [ ] **Step 3: Implement the additions in `tabulate.py`**

```python
# add to src/nsight/tabulate.py
def awareness_by_brand(frame: pd.DataFrame, *, brand_vars: dict[str, str],
                       positive_values: list[float] | None = None,
                       weight: str | None = None) -> dict[str, ShareResult]:
    pos = positive_values or [1.0]
    return {brand: share(frame, var=var, positive_values=pos, weight=weight)
            for brand, var in brand_vars.items()}


def top_of_mind(frame: pd.DataFrame, *, first_mention_var: str, brand: str,
                weight: str | None = None) -> ShareResult:
    s = frame[first_mention_var].astype("string").str.strip().str.casefold()
    target = brand.strip().casefold()
    w = pd.to_numeric(frame[weight], errors="coerce") if weight else pd.Series(1.0, index=frame.index)
    valid = s.notna()
    total = w[valid].sum()
    hit = w[valid & (s == target)].sum()
    raw = (hit / total * 100.0) if total else 0.0
    return ShareResult(pct=round(raw), n=int(valid.sum()), raw=raw)
```

- [ ] **Step 4: Run all tabulate tests**

Run: `uv run pytest tests/test_tabulate.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/tabulate.py tests/test_tabulate.py
git commit -m "feat: awareness_by_brand + top_of_mind"
```

---

### Task 1.4: Bind real Attendo variables and confirm weighting + segments

**Files:**
- Create: `src/nsight/attendo_bindings.py` (the survey-specific mapping)
- Test: `tests/test_golden_attendo.py`

This task resolves the runtime unknowns (which variable = which brand/segment, weighted vs unweighted) **against the original deck**. Use the deck's printed numbers as ground truth.

- [ ] **Step 1: Explore the codebook to map brands/segments**

Run: `uv run python -c "from nsight.codebook import Codebook; from nsight import config; cb=Codebook.load(config.CODEBOOK_JSON); import json; print(json.dumps({v:cb.label_of(v) for v in cb.columns}, ensure_ascii=False, indent=1))" | less`
Identify: the aided-awareness variables per brand (labels reference "tunnet vähintään nimeltä"), the experience/segment variables, any weight variable, and the first-mention variable. Record findings as a dict.

- [ ] **Step 2: Read the original deck's aided-awareness numbers (ground truth)**

Run: `uv run python scripts/peek_chart.py` — write a 10-line throwaway script that opens `config.ATTENDO_TEMPLATE` with `pptx`, finds slide 15/16 (aided awareness), and prints chart categories + values. These are the target percentages.

- [ ] **Step 3: Write the golden test asserting computed == deck (both weight policies tried)**

```python
# tests/test_golden_attendo.py
import pytest
from nsight import config
from nsight.store.survey_store import SurveyStore
from nsight.tabulate import awareness_by_brand


@pytest.mark.integration
def test_aided_awareness_matches_deck():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo files not present")
    store = SurveyStore(db_path=config.SURVEY_DB, codebook_path=config.CODEBOOK_JSON)
    if store.frame().empty:
        store.ingest(config.ATTENDO_SAV)
    from nsight.attendo_bindings import AIDED_AWARENESS_VARS, WEIGHT_VAR, DECK_AIDED_AWARENESS
    frame = store.frame()
    res = awareness_by_brand(frame, brand_vars=AIDED_AWARENESS_VARS, weight=WEIGHT_VAR)
    for brand, expected_pct in DECK_AIDED_AWARENESS.items():
        assert res[brand].pct == expected_pct, f"{brand}: got {res[brand].pct}, want {expected_pct}"
```

- [ ] **Step 4: Implement `attendo_bindings.py` with the real mapping**

Fill from Steps 1–2. `WEIGHT_VAR = None` initially (unweighted hypothesis); if the test fails, set it to the weight variable you found and re-run. `DECK_AIDED_AWARENESS` is the dict of brand→percent read from the deck.

```python
# src/nsight/attendo_bindings.py  (values filled from Steps 1-2)
AIDED_AWARENESS_VARS: dict[str, str] = {
    # "Attendo": "<var>", "Esperi": "<var>", ...
}
WEIGHT_VAR: str | None = None
DECK_AIDED_AWARENESS: dict[str, int] = {
    # "Attendo": 92, ...  (whole-percent from the deck)
}
```

- [ ] **Step 5: Run the golden test; iterate weighting/segment bindings until it passes**

Run: `uv run pytest tests/test_golden_attendo.py -v -m integration`
Expected: PASS. If off by a constant pattern, flip `WEIGHT_VAR`. If off for one segment, fix that segment's predicate in `segments.py` (add `ammattilaiset`/`suosittelijat` here). **Record the resolved weighting policy and segment rules in spec §10.**

- [ ] **Step 6: Commit** (checkpoint)

```bash
git add src/nsight/attendo_bindings.py src/nsight/segments.py tests/test_golden_attendo.py
git commit -m "feat: real Attendo variable bindings; aided awareness matches deck"
```

---

## Milestone 2 — Render layer (fill the fixed template in place)

### Task 2.1: Template indexing

**Files:**
- Create: `src/nsight/render/__init__.py` (empty)
- Create: `src/nsight/render/template.py`
- Test: `tests/test_render_chart.py` (shares fixtures with later render tasks)

- [ ] **Step 1: Write a fixture building a tiny 1-slide pptx with a named bar chart**

```python
# add to tests/conftest.py
import pytest
from pathlib import Path


@pytest.fixture
def chart_pptx(tmp_path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Inches
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    data = CategoryChartData()
    data.categories = ["Attendo", "Esperi"]
    data.add_series("Series 1", (0.1, 0.2))
    gf = slide.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED,
                                Inches(1), Inches(1), Inches(5), Inches(4), data)
    gf.name = "awareness_chart"
    out = tmp_path / "tmpl.pptx"
    prs.save(out)
    return out
```

- [ ] **Step 2: Write the failing test**

```python
# tests/test_render_chart.py
from nsight.render.template import Template


def test_template_finds_shape_by_slide_and_name(chart_pptx):
    tmpl = Template(chart_pptx)
    shape = tmpl.shape(slide_idx=0, name="awareness_chart")
    assert shape.has_chart
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_render_chart.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 4: Implement `template.py`**

```python
# src/nsight/render/template.py
from __future__ import annotations

from pathlib import Path

from pptx import Presentation


class Template:
    """Open a .pptx and address shapes by (slide index, shape name)."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self.prs = Presentation(str(self._path))

    def shape(self, *, slide_idx: int, name: str):
        slide = self.prs.slides[slide_idx]
        for sh in slide.shapes:
            if sh.name == name:
                return sh
        raise KeyError(f"shape {name!r} not found on slide {slide_idx}")

    def save(self, out_path: Path) -> None:
        self.prs.save(str(out_path))
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_render_chart.py -v`
Expected: PASS.

- [ ] **Step 6: Commit** (checkpoint)

```bash
git add src/nsight/render tests/test_render_chart.py tests/conftest.py
git commit -m "feat: template shape indexing"
```

---

### Task 2.2: Chart fill

**Files:**
- Create: `src/nsight/render/fill_chart.py`
- Test: `tests/test_render_chart.py` (add)

- [ ] **Step 1: Add the failing test**

```python
# append to tests/test_render_chart.py
from nsight.render.fill_chart import fill_chart


def test_fill_chart_replaces_values(chart_pptx, tmp_path):
    tmpl = Template(chart_pptx)
    shape = tmpl.shape(slide_idx=0, name="awareness_chart")
    fill_chart(shape, categories=["Attendo", "Esperi"], series={"Series 1": [0.75, 0.25]})
    out = tmp_path / "out.pptx"
    tmpl.save(out)

    from pptx import Presentation
    chart = [s for s in Presentation(str(out)).slides[0].shapes if s.has_chart][0].chart
    plot = chart.plots[0]
    assert list(plot.categories) == ["Attendo", "Esperi"]
    assert list(plot.series[0].values) == [0.75, 0.25]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_render_chart.py::test_fill_chart_replaces_values -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `fill_chart.py`**

```python
# src/nsight/render/fill_chart.py
from __future__ import annotations

from pptx.chart.data import CategoryChartData


def fill_chart(shape, *, categories: list[str], series: dict[str, list[float]]) -> None:
    """Replace a native chart's data in place, preserving its type and styling.

    Keep the number of series and categories equal to the template's so per-point
    formatting (colors, data labels) survives.
    """
    if not shape.has_chart:
        raise ValueError(f"shape {shape.name!r} is not a chart")
    data = CategoryChartData()
    data.categories = categories
    for name, values in series.items():
        data.add_series(name, tuple(values))
    shape.chart.replace_data(data)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_render_chart.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/render/fill_chart.py tests/test_render_chart.py
git commit -m "feat: chart fill"
```

---

### Task 2.3: Table fill

**Files:**
- Create: `src/nsight/render/fill_table.py`
- Test: `tests/test_render_table.py`

- [ ] **Step 1: Fixture + failing test**

```python
# tests/test_render_table.py
import pytest
from pathlib import Path
from nsight.render.template import Template
from nsight.render.fill_table import fill_table


@pytest.fixture
def table_pptx(tmp_path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    gf = slide.shapes.add_table(2, 2, Inches(1), Inches(1), Inches(4), Inches(2))
    gf.name = "awareness_table"
    out = tmp_path / "t.pptx"
    prs.save(out)
    return out


def test_fill_table_sets_cells(table_pptx, tmp_path):
    tmpl = Template(table_pptx)
    shape = tmpl.shape(slide_idx=0, name="awareness_table")
    fill_table(shape, {(0, 0): "Attendo", (0, 1): "92 %", (1, 1): "-1 %"})
    out = tmp_path / "o.pptx"
    tmpl.save(out)

    from pptx import Presentation
    tbl = [s for s in Presentation(str(out)).slides[0].shapes if s.has_table][0].table
    assert tbl.cell(0, 1).text == "92 %"
    assert tbl.cell(1, 1).text == "-1 %"
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_render_table.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `fill_table.py`**

```python
# src/nsight/render/fill_table.py
from __future__ import annotations


def fill_table(shape, cells: dict[tuple[int, int], str]) -> None:
    """Write text into specific (row, col) cells of a table, preserving formatting.

    Sets the text of the cell's first run when present (keeps font), else paragraph text.
    """
    if not shape.has_table:
        raise ValueError(f"shape {shape.name!r} is not a table")
    table = shape.table
    for (r, c), value in cells.items():
        cell = table.cell(r, c)
        para = cell.text_frame.paragraphs[0]
        if para.runs:
            para.runs[0].text = value
            for extra in para.runs[1:]:
                extra.text = ""
        else:
            para.text = value
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_render_table.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/render/fill_table.py tests/test_render_table.py
git commit -m "feat: table fill"
```

---

### Task 2.4: Text-box fill

**Files:**
- Create: `src/nsight/render/fill_text.py`
- Test: `tests/test_render_text.py`

- [ ] **Step 1: Fixture + failing test**

```python
# tests/test_render_text.py
import pytest
from pathlib import Path
from nsight.render.template import Template
from nsight.render.fill_text import set_text


@pytest.fixture
def text_pptx(tmp_path: Path) -> Path:
    from pptx import Presentation
    from pptx.util import Inches
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    tb = slide.shapes.add_textbox(Inches(1), Inches(1), Inches(4), Inches(1))
    tb.name = "key_message"
    tb.text_frame.text = "PLACEHOLDER"
    out = tmp_path / "x.pptx"
    prs.save(out)
    return out


def test_set_text_replaces_first_paragraph_keeping_box(text_pptx, tmp_path):
    tmpl = Template(text_pptx)
    shape = tmpl.shape(slide_idx=0, name="key_message")
    set_text(shape, "Attendo on tunnetuin.")
    out = tmp_path / "o.pptx"
    tmpl.save(out)
    from pptx import Presentation
    sh = [s for s in Presentation(str(out)).slides[0].shapes if s.name == "key_message"][0]
    assert sh.text_frame.text == "Attendo on tunnetuin."
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_render_text.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `fill_text.py`**

```python
# src/nsight/render/fill_text.py
from __future__ import annotations


def set_text(shape, value: str) -> None:
    """Replace a text box's content with `value`, preserving the first run's font."""
    if not shape.has_text_frame:
        raise ValueError(f"shape {shape.name!r} has no text frame")
    tf = shape.text_frame
    para = tf.paragraphs[0]
    if para.runs:
        para.runs[0].text = value
        for extra in para.runs[1:]:
            extra.text = ""
    else:
        para.text = value
    # clear any trailing paragraphs
    for p in list(tf.paragraphs[1:]):
        p._p.getparent().remove(p._p)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_render_text.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/render/fill_text.py tests/test_render_text.py
git commit -m "feat: text-box fill"
```

---

### Task 2.5: Renderer — apply a SlideFill spec

**Files:**
- Create: `src/nsight/render/renderer.py`
- Test: `tests/test_render_chart.py` (add an end-to-end fill test)

- [ ] **Step 1: Add failing test**

```python
# append to tests/test_render_chart.py
from nsight.render.renderer import SlideFill, ChartFill, render


def test_render_applies_chart_fill(chart_pptx, tmp_path):
    out = tmp_path / "rendered.pptx"
    render(
        template_path=chart_pptx,
        out_path=out,
        fills=[SlideFill(slide_idx=0, charts=[
            ChartFill(name="awareness_chart", categories=["Attendo", "Esperi"],
                      series={"Series 1": [0.9, 0.1]})
        ])],
    )
    from pptx import Presentation
    chart = [s for s in Presentation(str(out)).slides[0].shapes if s.has_chart][0].chart
    assert list(chart.plots[0].series[0].values) == [0.9, 0.1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_render_chart.py::test_render_applies_chart_fill -v`
Expected: FAIL `ImportError`.

- [ ] **Step 3: Implement `renderer.py`**

```python
# src/nsight/render/renderer.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from nsight.render.fill_chart import fill_chart
from nsight.render.fill_table import fill_table
from nsight.render.fill_text import set_text
from nsight.render.template import Template


@dataclass
class ChartFill:
    name: str
    categories: list[str]
    series: dict[str, list[float]]


@dataclass
class TableFill:
    name: str
    cells: dict[tuple[int, int], str]


@dataclass
class TextFill:
    name: str
    value: str


@dataclass
class SlideFill:
    slide_idx: int
    charts: list[ChartFill] = field(default_factory=list)
    tables: list[TableFill] = field(default_factory=list)
    texts: list[TextFill] = field(default_factory=list)


def render(*, template_path: Path, out_path: Path, fills: list[SlideFill]) -> Path:
    tmpl = Template(template_path)
    for sf in fills:
        for cf in sf.charts:
            fill_chart(tmpl.shape(slide_idx=sf.slide_idx, name=cf.name),
                       categories=cf.categories, series=cf.series)
        for tf in sf.tables:
            fill_table(tmpl.shape(slide_idx=sf.slide_idx, name=tf.name), tf.cells)
        for xf in sf.texts:
            set_text(tmpl.shape(slide_idx=sf.slide_idx, name=xf.name), xf.value)
    tmpl.save(out_path)
    return out_path
```

- [ ] **Step 4: Run all render tests**

Run: `uv run pytest tests/test_render_chart.py tests/test_render_table.py tests/test_render_text.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/render/renderer.py tests/test_render_chart.py
git commit -m "feat: renderer applies SlideFill specs"
```

---

## Milestone 3 — Fidelity harness (the scoreboard)

### Task 3.1: Extract structured content from a .pptx

**Files:**
- Create: `src/nsight/fidelity/__init__.py` (empty)
- Create: `src/nsight/fidelity/extract.py`
- Test: `tests/test_fidelity_extract.py`

- [ ] **Step 1: Failing test (reuse chart_pptx fixture)**

```python
# tests/test_fidelity_extract.py
from nsight.fidelity.extract import extract_deck


def test_extract_reads_chart_values(chart_pptx):
    deck = extract_deck(chart_pptx)
    s0 = deck.slides[0]
    assert s0.charts[0].categories == ["Attendo", "Esperi"]
    assert s0.charts[0].series["Series 1"] == [0.1, 0.2]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_fidelity_extract.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `extract.py`**

```python
# src/nsight/fidelity/extract.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pptx import Presentation


@dataclass
class ChartData:
    name: str
    categories: list[str]
    series: dict[str, list[float]]


@dataclass
class TableData:
    name: str
    cells: dict[tuple[int, int], str]


@dataclass
class SlideData:
    idx: int
    charts: list[ChartData] = field(default_factory=list)
    tables: list[TableData] = field(default_factory=list)
    texts: list[str] = field(default_factory=list)


@dataclass
class DeckData:
    slides: list[SlideData]


def extract_deck(path: Path) -> DeckData:
    prs = Presentation(str(path))
    slides: list[SlideData] = []
    for i, slide in enumerate(prs.slides):
        sd = SlideData(idx=i)
        for sh in slide.shapes:
            if sh.has_chart:
                plot = sh.chart.plots[0]
                series = {s.name: list(s.values) for s in plot.series}
                sd.charts.append(ChartData(name=sh.name,
                                           categories=[str(c) for c in plot.categories],
                                           series=series))
            elif sh.has_table:
                cells = {}
                for r, row in enumerate(sh.table.rows):
                    for c, cell in enumerate(row.cells):
                        cells[(r, c)] = cell.text
                sd.tables.append(TableData(name=sh.name, cells=cells))
            elif sh.has_text_frame and sh.text_frame.text.strip():
                sd.texts.append(sh.text_frame.text)
        slides.append(sd)
    return DeckData(slides=slides)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_fidelity_extract.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/fidelity tests/test_fidelity_extract.py
git commit -m "feat: extract structured content from pptx"
```

---

### Task 3.2: Compare two decks → fidelity report

**Files:**
- Create: `src/nsight/fidelity/compare.py`
- Test: `tests/test_fidelity_compare.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_fidelity_compare.py
from nsight.fidelity.extract import DeckData, SlideData, ChartData
from nsight.fidelity.compare import compare_decks


def _deck(v):
    return DeckData(slides=[SlideData(idx=0, charts=[
        ChartData(name="c", categories=["Attendo"], series={"S": [v]})])])


def test_identical_decks_score_100():
    rep = compare_decks(_deck(0.92), _deck(0.92))
    assert rep.chart_score == 100.0
    assert rep.charts_matched == 1


def test_value_within_rounding_tolerance_matches():
    rep = compare_decks(_deck(0.921), _deck(0.918))  # both round to 92%
    assert rep.chart_score == 100.0


def test_value_off_by_more_than_one_pct_fails():
    rep = compare_decks(_deck(0.92), _deck(0.80))
    assert rep.chart_score == 0.0
    assert rep.mismatches  # non-empty
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_fidelity_compare.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `compare.py`**

```python
# src/nsight/fidelity/compare.py
from __future__ import annotations

from dataclasses import dataclass, field

from nsight.fidelity.extract import DeckData


@dataclass
class FidelityReport:
    chart_score: float
    charts_matched: int
    charts_total: int
    mismatches: list[str] = field(default_factory=list)


def _as_pct(v: float) -> float:
    # chart values are stored as proportions (0..1) or already percents; normalize to percent
    return round(v * 100) if abs(v) <= 1.0 else round(v)


def compare_decks(generated: DeckData, original: DeckData) -> FidelityReport:
    matched = 0
    total = 0
    mismatches: list[str] = []
    for og_slide in original.slides:
        gen_slide = next((s for s in generated.slides if s.idx == og_slide.idx), None)
        for og_chart in og_slide.charts:
            gen_chart = None
            if gen_slide:
                gen_chart = next((c for c in gen_slide.charts if c.name == og_chart.name), None)
            for sname, ovals in og_chart.series.items():
                for j, oval in enumerate(ovals):
                    total += 1
                    gval = None
                    if gen_chart and sname in gen_chart.series and j < len(gen_chart.series[sname]):
                        gval = gen_chart.series[sname][j]
                    if gval is not None and _as_pct(gval) == _as_pct(oval):
                        matched += 1
                    else:
                        mismatches.append(
                            f"slide {og_slide.idx} chart {og_chart.name} [{sname}][{j}]: "
                            f"got {gval}, want {oval}")
    score = (matched / total * 100.0) if total else 0.0
    return FidelityReport(chart_score=round(score, 1), charts_matched=matched,
                          charts_total=total, mismatches=mismatches)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_fidelity_compare.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/fidelity/compare.py tests/test_fidelity_compare.py
git commit -m "feat: deck fidelity comparison"
```

---

## Milestone 4 — Wave history & open-ended coding

### Task 4.1: Wave history store

**Files:**
- Create: `src/nsight/waves.py`
- Test: `tests/test_waves.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_waves.py
from nsight.waves import WaveHistory


def test_store_and_delta(tmp_path):
    wh = WaveHistory(tmp_path / "waves.json")
    wh.set("2025-05", "aided_awareness", "Attendo", 93)
    wh.set("2025-11", "aided_awareness", "Attendo", 92)
    assert wh.get("2025-05", "aided_awareness", "Attendo") == 93
    assert wh.delta(current=92, prior_wave="2025-05", metric="aided_awareness", key="Attendo") == -1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_waves.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `waves.py`**

```python
# src/nsight/waves.py
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
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_waves.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/waves.py tests/test_waves.py
git commit -m "feat: wave history store + deltas"
```

---

### Task 4.2: Extract historical waves from the original deck (one-time)

**Files:**
- Create: `scripts/extract_waves.py`
- Test: manual / integration

- [ ] **Step 1: Write the extractor script**

```python
# scripts/extract_waves.py
"""One-time: read prior-wave numbers printed in the original Attendo deck into waves.json.

The deck prints prior waves in text (e.g. "touko 25: 55 %") and in trend tables. This
script extracts the aided-awareness series and the perception trend callouts. Run once;
the result feeds trend reproduction. Manual verification against the deck is required.
"""
from nsight import config
from nsight.fidelity.extract import extract_deck
from nsight.waves import WaveHistory


def main() -> None:
    deck = extract_deck(config.ATTENDO_TEMPLATE)
    wh = WaveHistory(config.WAVES_JSON)
    # Aided awareness current wave from slide 15/16 charts -> store as 2025-11 baseline.
    # (Fill slide indices + brand order after inspecting the deck.)
    print("Slides with charts:", [s.idx for s in deck.slides if s.charts])
    print("Edit this script to map slide charts -> (wave, metric, brand) and call wh.set(...).")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run, inspect, and fill the mapping**

Run: `uv run python scripts/extract_waves.py`
Then edit to map the deck's printed prior-wave numbers (read from the chart/table/text content the script prints) into `wh.set(...)` calls. Re-run until `work/waves.json` contains the prior-wave aided-awareness and perception numbers.

- [ ] **Step 3: Verify against the deck by eye**

Open the original deck; confirm 3–5 stored numbers match the printed "touko 25 / marras 24" values. Record any deck text that couldn't be parsed.

- [ ] **Step 4: Commit** (checkpoint)

```bash
git add scripts/extract_waves.py
git commit -m "feat: wave extraction script (waves.json is gitignored output)"
```

---

### Task 4.3: Open-ended coding tool

**Files:**
- Create: `src/nsight/coding.py`
- Test: `tests/test_coding.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_coding.py
import pandas as pd
from nsight.coding import top_words


def test_top_words_normalizes_and_counts():
    frame = pd.DataFrame({"w1": ["Kallis", "kallis ", "Luotettava", "KALLIS", "hyvä"],
                          "w2": ["luotettava", None, "kallis", None, None]})
    res = top_words(frame, text_vars=["w1", "w2"], top_n=2)
    # kallis appears 4x (3 in w1 + 1 in w2), luotettava 2x
    assert res[0] == ("kallis", 4)
    assert res[1] == ("luotettava", 2)


def test_top_words_respects_top_n():
    frame = pd.DataFrame({"w": ["a", "a", "b", "c"]})
    assert len(top_words(frame, text_vars=["w"], top_n=1)) == 1
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_coding.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `coding.py`**

```python
# src/nsight/coding.py
from __future__ import annotations

from collections import Counter

import pandas as pd


def _normalize(token: str) -> str:
    return token.strip().casefold()


def top_words(frame: pd.DataFrame, *, text_vars: list[str], top_n: int = 10,
              synonyms: dict[str, str] | None = None) -> list[tuple[str, int]]:
    """Count normalized free-text tokens across the given variables, return TOP-N.

    `synonyms` collapses variants to a canonical form (resolve against the deck's
    coding scheme in Task 4.4). Counting is case/space-insensitive.
    """
    syn = synonyms or {}
    counter: Counter[str] = Counter()
    for var in text_vars:
        for val in frame[var].dropna().astype(str):
            tok = _normalize(val)
            if not tok:
                continue
            counter[syn.get(tok, tok)] += 1
    return counter.most_common(top_n)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_coding.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/coding.py tests/test_coding.py
git commit -m "feat: open-ended response coding (TOP-N words)"
```

---

### Task 4.4: Golden test for brand-image TOP-10 (slide 25)

**Files:**
- Test: `tests/test_golden_attendo.py` (add)
- Modify: `src/nsight/attendo_bindings.py` (add image word vars + synonyms + deck TOP-10)

- [ ] **Step 1: Read slide 25's printed TOP-10 from the deck** (e.g. "Kallis (188), Kiireinen (68)…"). Record as `DECK_IMAGE_TOP10`.

- [ ] **Step 2: Add the failing golden test**

```python
# append to tests/test_golden_attendo.py
from nsight.coding import top_words


@pytest.mark.integration
def test_brand_image_top10_overlaps_deck():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo files not present")
    store = SurveyStore(db_path=config.SURVEY_DB, codebook_path=config.CODEBOOK_JSON)
    if store.frame().empty:
        store.ingest(config.ATTENDO_SAV)
    from nsight.attendo_bindings import IMAGE_WORD_VARS, IMAGE_SYNONYMS, DECK_IMAGE_TOP10
    res = top_words(store.frame(), text_vars=IMAGE_WORD_VARS, top_n=10, synonyms=IMAGE_SYNONYMS)
    got = [w for w, _ in res]
    overlap = len(set(got) & set(DECK_IMAGE_TOP10))
    assert overlap >= 7, f"only {overlap}/10 overlap; got {got}"
```

- [ ] **Step 3: Fill the bindings; iterate synonyms until overlap ≥ 7/10**

Identify the open-ended image variables in the codebook (labels reference "Millä kolmella sanalla"). Set `IMAGE_WORD_VARS`. Add `IMAGE_SYNONYMS` to match the deck's coding (e.g. collapse inflections). Run:
Run: `uv run pytest tests/test_golden_attendo.py::test_brand_image_top10_overlaps_deck -v -m integration`
Expected: PASS at ≥7/10 overlap. Record the coding scheme in spec §10.

- [ ] **Step 4: Commit** (checkpoint)

```bash
git add tests/test_golden_attendo.py src/nsight/attendo_bindings.py
git commit -m "feat: brand-image TOP-10 coding matches deck (>=7/10)"
```

---

## Milestone 5 — Brief & agent orchestration

### Task 5.1: Brief model + parser

**Files:**
- Create: `src/nsight/brief.py`
- Create: `briefs/attendo.md` (start with 1–2 sections; grow in Task 5.4)
- Test: `tests/test_brief.py`

The brief is Markdown with one YAML block per slide job, binding a brief item to a template slide + shapes.

- [ ] **Step 1: Failing test**

```python
# tests/test_brief.py
from nsight.brief import parse_brief

SAMPLE = '''
# Attendo brief

```slide
id: aided_awareness
slide_idx: 14
title: Aided awareness
metric: aided_awareness
segment: kaikki
chart: { name: "awareness_chart", brands: ["Attendo", "Esperi"] }
key_message: { name: "key_message" }
```
'''


def test_parse_brief_extracts_jobs(tmp_path):
    p = tmp_path / "b.md"
    p.write_text(SAMPLE)
    brief = parse_brief(p)
    assert len(brief.jobs) == 1
    job = brief.jobs[0]
    assert job.id == "aided_awareness"
    assert job.slide_idx == 14
    assert job.metric == "aided_awareness"
    assert job.chart["brands"] == ["Attendo", "Esperi"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_brief.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `brief.py`**

```python
# src/nsight/brief.py
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

_BLOCK = re.compile(r"```slide\n(.*?)```", re.S)


@dataclass
class SlideJob:
    id: str
    slide_idx: int
    metric: str
    segment: str = "kaikki"
    title: str | None = None
    chart: dict | None = None
    table: dict | None = None
    key_message: dict | None = None
    raw: dict = field(default_factory=dict)


@dataclass
class Brief:
    jobs: list[SlideJob]


def parse_brief(path: Path) -> Brief:
    text = Path(path).read_text()
    jobs: list[SlideJob] = []
    for m in _BLOCK.finditer(text):
        d = yaml.safe_load(m.group(1)) or {}
        jobs.append(SlideJob(
            id=d["id"], slide_idx=int(d["slide_idx"]), metric=d["metric"],
            segment=d.get("segment", "kaikki"), title=d.get("title"),
            chart=d.get("chart"), table=d.get("table"),
            key_message=d.get("key_message"), raw=d))
    return Brief(jobs=jobs)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_brief.py -v`
Expected: PASS.

- [ ] **Step 5: Create `briefs/attendo.md` with the aided-awareness section** (real `slide_idx`/shape names from the template; expand later). Then **Commit** (checkpoint):

```bash
git add src/nsight/brief.py briefs/attendo.md tests/test_brief.py
git commit -m "feat: brief model + parser"
```

---

### Task 5.2: Deterministic deck builder (no LLM) + binding pre-flight

**Files:**
- Create: `src/nsight/build.py`
- Test: `tests/test_build.py`

This wires brief jobs → tabulation → SlideFill, fully deterministically. The agent (Task 5.3) reuses these functions; building them LLM-free first makes them testable and makes the agent's job pure routing + prose.

- [ ] **Step 1: Failing test**

```python
# tests/test_build.py
import pandas as pd
from nsight.brief import SlideJob
from nsight.build import build_slidefill


def test_build_aided_awareness_slidefill():
    frame = pd.DataFrame({"aw_attendo": [1, 1, 1, 0], "aw_esperi": [1, 0, 0, 0]})
    job = SlideJob(id="aw", slide_idx=14, metric="aided_awareness", segment="kaikki",
                   chart={"name": "awareness_chart", "brands": ["Attendo", "Esperi"]})
    fill = build_slidefill(
        job, frame,
        brand_vars={"Attendo": "aw_attendo", "Esperi": "aw_esperi"},
        weight=None,
    )
    assert fill.slide_idx == 14
    cf = fill.charts[0]
    assert cf.name == "awareness_chart"
    assert cf.categories == ["Attendo", "Esperi"]
    assert cf.series["osuus"] == [75.0, 25.0]
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_build.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `build.py`**

```python
# src/nsight/build.py
from __future__ import annotations

import pandas as pd

from nsight.brief import SlideJob
from nsight.render.renderer import ChartFill, SlideFill, TextFill
from nsight.segments import segment_mask
from nsight.tabulate import awareness_by_brand


def build_slidefill(job: SlideJob, frame: pd.DataFrame, *, brand_vars: dict[str, str],
                    weight: str | None, key_message: str | None = None) -> SlideFill:
    mask = segment_mask(job.segment, frame) if job.segment else pd.Series(True, index=frame.index)
    seg = frame[mask]
    fill = SlideFill(slide_idx=job.slide_idx)

    if job.metric == "aided_awareness" and job.chart:
        brands = job.chart["brands"]
        selected = {b: brand_vars[b] for b in brands}
        res = awareness_by_brand(seg, brand_vars=selected, weight=weight)
        fill.charts.append(ChartFill(
            name=job.chart["name"], categories=brands,
            series={"osuus": [float(res[b].pct) for b in brands]}))
    else:
        raise ValueError(f"unsupported metric for build: {job.metric}")

    if job.key_message and key_message:
        fill.texts.append(TextFill(name=job.key_message["name"], value=key_message))
    return fill


def preflight(jobs, template) -> list[str]:
    """Return a list of binding errors: brief targets that don't resolve in the template."""
    errors: list[str] = []
    for job in jobs:
        for spec in (job.chart, job.table, job.key_message):
            if not spec:
                continue
            try:
                template.shape(slide_idx=job.slide_idx, name=spec["name"])
            except KeyError as e:
                errors.append(f"job {job.id}: {e}")
    return errors
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_build.py -v`
Expected: PASS.

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/build.py tests/test_build.py
git commit -m "feat: deterministic slidefill builder + binding preflight"
```

---

### Task 5.3: Agent tools + workflow

**Files:**
- Create: `src/nsight/agent/__init__.py` (empty)
- Create: `src/nsight/agent/tools.py`
- Create: `src/nsight/agent/workflow.py`
- Test: `tests/test_agent_workflow.py`

The agent's job: for each brief job, call the deterministic build tool to get numbers, write a Finnish `key_message`, and collect SlideFills. Numbers come only from tools.

- [ ] **Step 1: Failing test (workflow runs deterministically without network using a stub narrator)**

```python
# tests/test_agent_workflow.py
import pandas as pd
from nsight.brief import Brief, SlideJob
from nsight.agent.workflow import generate_fills


def test_generate_fills_uses_tools_for_numbers():
    frame = pd.DataFrame({"aw_attendo": [1, 1, 1, 0], "aw_esperi": [1, 0, 0, 0]})
    brief = Brief(jobs=[SlideJob(id="aw", slide_idx=14, metric="aided_awareness",
                                 segment="kaikki",
                                 chart={"name": "awareness_chart", "brands": ["Attendo", "Esperi"]},
                                 key_message={"name": "key_message"})])
    # narrator stub avoids an LLM call in the unit test
    fills = generate_fills(brief, frame,
                           brand_vars={"Attendo": "aw_attendo", "Esperi": "aw_esperi"},
                           weight=None,
                           narrator=lambda job, numbers: "Attendo on tunnetuin.")
    assert fills[0].charts[0].series["osuus"] == [75.0, 25.0]
    assert fills[0].texts[0].value == "Attendo on tunnetuin."
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_agent_workflow.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `workflow.py` (narrator injectable; real narrator calls the SDK)**

```python
# src/nsight/agent/workflow.py
from __future__ import annotations

from typing import Callable

import pandas as pd

from nsight.brief import Brief
from nsight.build import build_slidefill
from nsight.render.renderer import SlideFill

Narrator = Callable[[object, dict], str]


def generate_fills(brief: Brief, frame: pd.DataFrame, *, brand_vars: dict[str, str],
                   weight: str | None, narrator: Narrator) -> list[SlideFill]:
    fills: list[SlideFill] = []
    for job in brief.jobs:
        # First build numbers deterministically (also gives us the figures to narrate).
        base = build_slidefill(job, frame, brand_vars=brand_vars, weight=weight)
        numbers = {cf.name: dict(zip(cf.categories, cf.series["osuus"])) for cf in base.charts}
        message = narrator(job, numbers) if job.key_message else None
        fill = build_slidefill(job, frame, brand_vars=brand_vars, weight=weight,
                               key_message=message)
        fills.append(fill)
    return fills
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_agent_workflow.py -v`
Expected: PASS.

- [ ] **Step 5: Implement the real SDK narrator in `tools.py`**

```python
# src/nsight/agent/tools.py
from __future__ import annotations

import anyio
from claude_agent_sdk import ClaudeAgentOptions, query


def sdk_narrator(job, numbers: dict) -> str:
    """Ask Claude to write a one-sentence Finnish key message from already-computed numbers.

    Numbers are passed in the prompt; the model NEVER computes them.
    """
    prompt = (
        "Olet markkinatutkimuksen analyytikko. Kirjoita YKSI ytimekäs suomenkielinen "
        "avainviesti dian otsikoksi. Käytä VAIN annettuja lukuja, älä keksi uusia.\n"
        f"Dia: {job.title or job.id}\nLuvut: {numbers}\n"
        "Palauta vain virke, ei muuta."
    )

    async def _run() -> str:
        out = []
        async for msg in query(prompt=prompt, options=ClaudeAgentOptions(max_turns=1)):
            text = getattr(msg, "result", None) or getattr(msg, "text", None)
            if text:
                out.append(text)
        return " ".join(out).strip() or (job.title or "")

    return anyio.run(_run)
```

- [ ] **Step 6: Commit** (checkpoint)

```bash
git add src/nsight/agent tests/test_agent_workflow.py
git commit -m "feat: agent workflow (deterministic numbers + injectable narrator)"
```

---

### Task 5.4: End-to-end generation entrypoint + grow the brief

**Files:**
- Create: `src/nsight/generate.py`
- Modify: `briefs/attendo.md` (cover all data-bearing slides)
- Test: `tests/test_golden_attendo.py` (add full-deck fidelity test)

- [ ] **Step 1: Implement `generate.py`**

```python
# src/nsight/generate.py
from __future__ import annotations

from pathlib import Path

from nsight import config
from nsight.agent.tools import sdk_narrator
from nsight.agent.workflow import generate_fills
from nsight.brief import parse_brief
from nsight.build import preflight
from nsight.render.renderer import render
from nsight.render.template import Template
from nsight.store.survey_store import SurveyStore


def generate_deck(*, sav: Path, brief_path: Path, template: Path, out: Path,
                  narrator=sdk_narrator) -> Path:
    store = SurveyStore(db_path=config.SURVEY_DB, codebook_path=config.CODEBOOK_JSON)
    if store.frame().empty:
        store.ingest(sav)
    frame = store.frame()

    brief = parse_brief(brief_path)
    errors = preflight(brief.jobs, Template(template))
    if errors:
        raise ValueError("brief→template binding errors:\n" + "\n".join(errors))

    from nsight.attendo_bindings import AIDED_AWARENESS_VARS, WEIGHT_VAR
    fills = generate_fills(brief, frame, brand_vars=AIDED_AWARENESS_VARS,
                           weight=WEIGHT_VAR, narrator=narrator)
    return render(template_path=template, out_path=out, fills=fills)
```

- [ ] **Step 2: Grow `briefs/attendo.md`** to cover every data-bearing slide (charts, tables, word lists). For each, set the real `slide_idx` and shape `name` (read shape names from the template with a helper: `uv run python -c "from nsight.render.template import Template; from nsight import config; t=Template(config.ATTENDO_TEMPLATE); [print(i, [sh.name for sh in s.shapes]) for i,s in enumerate(t.prs.slides)]"`). Extend `build.py` to handle `perception_split`, `top_of_mind`, table fills (deltas via `WaveHistory`), and word lists (`coding.top_words`) as new `metric` branches — each added TDD-style with a unit test in `tests/test_build.py` before wiring into the brief.

- [ ] **Step 3: Add the full-deck golden fidelity test**

```python
# append to tests/test_golden_attendo.py
from nsight.generate import generate_deck
from nsight.fidelity.extract import extract_deck
from nsight.fidelity.compare import compare_decks


@pytest.mark.integration
def test_full_deck_fidelity():
    if not config.ATTENDO_SAV.exists():
        pytest.skip("Attendo files not present")
    out = config.GENERATED_PPTX
    generate_deck(sav=config.ATTENDO_SAV, brief_path=config.BRIEFS_DIR / "attendo.md",
                  template=config.ATTENDO_TEMPLATE, out=out,
                  narrator=lambda job, numbers: job.title or job.id)  # offline narrator
    rep = compare_decks(extract_deck(out), extract_deck(config.ATTENDO_TEMPLATE))
    print("chart fidelity:", rep.chart_score, "mismatches:", rep.mismatches[:10])
    assert rep.chart_score >= 90.0
```

- [ ] **Step 4: Iterate brief + bindings until chart fidelity ≥ 90%**

Run: `uv run pytest tests/test_golden_attendo.py::test_full_deck_fidelity -v -m integration -s`
Read the printed mismatches; fix bindings/segments/metric handling; re-run. This is the core quality loop — keep going until the threshold holds. Raise the threshold over time as coverage grows.

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/generate.py src/nsight/build.py briefs/attendo.md tests/test_golden_attendo.py tests/test_build.py
git commit -m "feat: end-to-end deck generation; chart fidelity >=90%"
```

---

## Milestone 6 — Web app

### Task 6.1: FastAPI backend

**Files:**
- Create: `src/nsight/webapp/__init__.py` (empty)
- Create: `src/nsight/webapp/app.py`
- Test: `tests/test_webapp.py`

- [ ] **Step 1: Failing test (use FastAPI TestClient; stub generation)**

```python
# tests/test_webapp.py
from fastapi.testclient import TestClient
from nsight.webapp.app import create_app


def test_list_inputs_endpoint(tmp_path, monkeypatch):
    app = create_app()
    client = TestClient(app)
    r = client.get("/api/inputs")
    assert r.status_code == 200
    body = r.json()
    assert "savs" in body and "briefs" in body


def test_run_returns_report(monkeypatch):
    import nsight.webapp.app as appmod

    def fake_run(sav, brief):
        return {"chart_score": 95.0, "mismatches": [], "deck_path": "/tmp/x.pptx"}

    monkeypatch.setattr(appmod, "run_generation", fake_run)
    client = TestClient(create_app())
    r = client.post("/api/run", json={"sav": "a.sav", "brief": "attendo.md"})
    assert r.status_code == 200
    assert r.json()["chart_score"] == 95.0
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_webapp.py -v`
Expected: FAIL `ModuleNotFoundError`.

- [ ] **Step 3: Implement `app.py`**

```python
# src/nsight/webapp/app.py
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from nsight import config
from nsight.fidelity.compare import compare_decks
from nsight.fidelity.extract import extract_deck
from nsight.generate import generate_deck


class RunRequest(BaseModel):
    sav: str
    brief: str


def run_generation(sav: str, brief: str) -> dict:
    out = generate_deck(
        sav=config.INPUT_DIR / sav, brief_path=config.BRIEFS_DIR / brief,
        template=config.ATTENDO_TEMPLATE, out=config.GENERATED_PPTX,
        narrator=lambda job, numbers: job.title or job.id,
    )
    rep = compare_decks(extract_deck(out), extract_deck(config.ATTENDO_TEMPLATE))
    return {"chart_score": rep.chart_score, "mismatches": rep.mismatches[:50],
            "deck_path": str(out)}


def create_app() -> FastAPI:
    app = FastAPI(title="nSight deck generator")

    @app.get("/api/inputs")
    def inputs() -> dict:
        return {"savs": [p.name for p in config.INPUT_DIR.glob("*.sav")],
                "briefs": [p.name for p in config.BRIEFS_DIR.glob("*.md")]}

    @app.post("/api/run")
    def run(req: RunRequest) -> dict:
        return run_generation(req.sav, req.brief)

    @app.get("/api/download")
    def download() -> FileResponse:
        return FileResponse(config.GENERATED_PPTX, filename="attendo_generated.pptx")

    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
    return app


app = create_app()
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_webapp.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit** (checkpoint)

```bash
git add src/nsight/webapp/app.py tests/test_webapp.py
git commit -m "feat: FastAPI backend for deck generation"
```

---

### Task 6.2: Minimal frontend

**Files:**
- Create: `src/nsight/webapp/static/index.html`

- [ ] **Step 1: Write `index.html`** — a single page that: fetches `/api/inputs` to populate two dropdowns (sav, brief), a "Generate" button that POSTs `/api/run` and shows a spinner, then renders the returned `chart_score` plus a collapsible mismatch list, and a "Download .pptx" link to `/api/download`.

```html
<!doctype html>
<html lang="fi">
<head><meta charset="utf-8"><title>nSight deck generator</title>
<style>body{font-family:system-ui;max-width:760px;margin:40px auto}button{padding:8px 16px}
.score{font-size:2rem;font-weight:700}.bad{color:#b00}.ok{color:#070}li{font-family:monospace}</style>
</head>
<body>
<h1>nSight deck generator</h1>
<label>Data <select id="sav"></select></label>
<label>Brief <select id="brief"></select></label>
<button id="go">Generate</button>
<div id="status"></div>
<div id="result" hidden>
  <p class="score" id="score"></p>
  <p><a id="dl" href="/api/download">Download .pptx</a></p>
  <details><summary>Mismatches</summary><ul id="miss"></ul></details>
</div>
<script>
async function load(){const r=await fetch('/api/inputs');const j=await r.json();
 for(const s of j.savs){sav.add(new Option(s,s))}
 for(const b of j.briefs){brief.add(new Option(b,b))}}
go.onclick=async()=>{status.textContent='Generating…';result.hidden=true;
 const r=await fetch('/api/run',{method:'POST',headers:{'Content-Type':'application/json'},
  body:JSON.stringify({sav:sav.value,brief:brief.value})});
 const j=await r.json();status.textContent='';result.hidden=false;
 score.textContent='Chart fidelity: '+j.chart_score+'%';
 score.className='score '+(j.chart_score>=90?'ok':'bad');
 miss.innerHTML='';for(const m of j.mismatches){const li=document.createElement('li');li.textContent=m;miss.appendChild(li)}}
load();
</script>
</body></html>
```

- [ ] **Step 2: Manual smoke test**

Run: `uv run uvicorn nsight.webapp.app:app --port 8800` then open `http://127.0.0.1:8800`. Select the Attendo sav + `attendo.md`, click Generate, confirm a score appears and the download works.

- [ ] **Step 3: Commit** (checkpoint)

```bash
git add src/nsight/webapp/static/index.html
git commit -m "feat: minimal web UI"
```

---

## Milestone 7 — Hardening & full-suite verification

### Task 7.1: Full test run + fidelity report

- [ ] **Step 1: Run the entire suite (unit + integration)**

Run: `uv run pytest -v` then `uv run pytest -v -m integration -s`
Expected: all green; the printed full-deck chart fidelity is at the target threshold. Record the final score.

- [ ] **Step 2: Open the generated deck and eyeball it** against the original (a few representative slides per carrier type: a bar chart, a radar chart, a table with deltas, a word-list slide). Note residual gaps in spec §10.

- [ ] **Step 3: Commit any fixes** (checkpoint).

---

## Self-review (completed by plan author)

**Spec coverage check:**
- §5.0 deck anatomy (43 bar/2 radar, 13 tables, slides 25–29 word lists) → render tasks 2.2/2.3/2.4, coding 4.3/4.4, extract 3.1. ✓
- §5.2 DataHive data plane (TabularStore, no aggregation, ABAC, in-process aggregation) → Task 0.2 (`frame()` reads all rows; aggregation in `tabulate.py`). ✓
- §5.3 engine (segments, weighting, categorical tools, open-ended coding, 3-mode render) → M1, M2, 4.3. ✓
- §5.4 agent orchestration + brief→template binding + pre-flight → 5.1/5.2/5.3. ✓
- §5.5 web app → M6. ✓
- §5.6 fidelity harness (charts + tables + word lists) → M3 (charts/tables extracted; word-list comparison via overlap is covered at the coding golden test 4.4; deck-level table/word diff can extend `compare.py` if needed). ✓ (note: `compare_decks` scores charts; table/word scoring is asserted via the golden tests 1.4/4.4 — extend `compare.py` with table/word scoring in 7.1 if a single combined score is wanted.)
- §8 build order → milestones M0–M6 follow it. ✓
- §9 risks (weighting, segments, coding) → resolved empirically in 1.4 and 4.4 with golden tests as gates. ✓

**Placeholder scan:** Variable bindings in `attendo_bindings.py` are intentionally filled at execution (Tasks 1.4/4.4) because they require reading the real codebook/deck; every such task has explicit discovery steps and a golden test gate, not a vague "TBD". No code step ships without code.

**Type consistency:** `ShareResult.pct` (rounded) used consistently; `SlideFill/ChartFill/TableFill/TextFill` names match between `renderer.py`, `build.py`, `workflow.py`; `DeckData/SlideData/ChartData` match between `extract.py` and `compare.py`; `SurveyStore(db_path, codebook_path)` signature consistent across store/golden/generate/webapp; `generate_deck(...)` and `generate_fills(...)` signatures match their callers.

**Identified follow-up (non-blocking):** `compare_decks` currently scores charts only; table/word-list fidelity is gated by the golden tests rather than folded into one number. Task 7.1 step notes the optional extension.
