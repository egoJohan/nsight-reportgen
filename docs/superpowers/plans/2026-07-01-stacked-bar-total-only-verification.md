# Stacked Bar "Total-Only" — Defect Fix & Verification Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow **stacked horizontal** and **stacked vertical** bar charts to be built *without* a classifying variable — rendering the question's answer distribution as a single 100%-stacked "Total" bar — and prove it with an extensive, manifest-first, locally-run verification suite.

**Architecture:** The defect has four coordinated root-cause sites (one declarative schema flag, two hard API `422` guards, and one degenerate renderer fallback). The fix relaxes all four. Verification is layered: pure-function **unit** tests on the renderer layout, **integration** tests on the stats→render path and the FastAPI routes, and **e2e** tests that run the *real product render path* (matplotlib image mode) over synthetic data plus the three real client SAV files. Every behavioural change is **manifested by a failing (RED) test before any production code is touched**, then driven GREEN by the fix.

**Tech Stack:** Python 3.13, FastAPI + `TestClient`, `pytest` (+ `pytest-asyncio`), pandas, matplotlib (image render), python-pptx, Pillow (pixel assertions), `pyreadstat` via `read_sav`. Frontend (`web/`, TypeScript/React) is **not** the render path in production and is out of scope for behavioural verification (it only reads the `required` flag from the schema JSON, which this plan flips).

---

## Global Constraints

- **LOCAL ONLY — never staging.** Every command in this plan runs on the local machine against the local checkout. No staging deploy, no `nsight.egohive.ai`, no live egoHive/datahive is touched by any verification step. The real-data e2e uses `NSIGHT_DEMO=1` (local filesystem store), not a live backend.
- **Real-SAV e2e is its own group.** Tests that exercise the local-filesystem demo path (`NSIGHT_DEMO=1`, `InMemoryDataHiveClient`) carry the new `@pytest.mark.demo` marker and **auto-skip unless `NSIGHT_DEMO=1`** is set. The standard suite (`pytest`) never requires a live backend; the demo group is invoked explicitly with `NSIGHT_DEMO=1 pytest -m demo`.
- **Product render path = image mode.** The web app sends `render_mode: "image"` (`web/src/lib/api.ts:180`). All render assertions target the matplotlib image builders. The `native` (python-pptx chart) path is legacy and explicitly out of scope.
- **IPR handling.** The three client SAVs already live (tracked) under `input/`. Runtime copies for the demo store go **only** to gitignored locations (`work/…` or a `tmp_path`). The e2e data dir `tests/rb/e2e/data/` is added to `.gitignore`; no new client binary is ever staged for commit. No git operation in this plan adds, moves, or pushes client data.
- **Manifest-first (TDD).** For each behavioural change: write/adjust a test that expresses the *desired* behaviour, run it, and **confirm it FAILS against unmodified production code** (RED) before applying the fix. Only then make it pass (GREEN). No production edit lands before its RED test exists.
- **No new dependencies.** Pillow, pandas, matplotlib, python-pptx, FastAPI TestClient are already in the dev environment.
- **Run tests from repo root** `/home/johan/Projects/nsight/proto` with the project venv active (`.venv`). Command form used throughout: `python -m pytest <path> -v`.

---

## Defect Statement & Root-Cause Map

**Symptom:** A user configuring a *stacked vertical/horizontal bar* is forced to pick a classifying variable. Omitting it yields an HTTP `422` ("Stacked charts need a classifying variable to define the segments"). The user's requirement: a stacked bar can legitimately show *just the total* — i.e. one bar whose stack is the question's answer categories, summing to 100% (the classic single-distribution bar).

**Desired behaviour (total-only stacked bar):** With no `classifying_var`, `compute()` returns `segments=("Total",)` and `categories=<answer options>`. The stacked renderer must draw **one bar** (the "Total" column) whose **stack members are the answer categories**, filling exactly 100%. Batteries already do this via their own path; single/multi questions must now do it too.

**Four root-cause sites (all must change):**

| # | File | Location | Current behaviour | Required behaviour |
|---|------|----------|-------------------|--------------------|
| 1 | `src/reportbuilder/render/config_schema.py` | `stacked_schema()` L144–146 → `classifying_var_field(required=True)` | Schema marks `classifying_var` **required** (red asterisk in UI; drives frontend "missing" state) | `classifying_var_field()` (optional, `required=False`) |
| 2 | `src/reportbuilder/api/routes_render.py` | `_STACKED` guard L81–98 (full-deck render) | Raises `422` when a stacked chart lacks `classifying_var` (battery-exempt) | Guard removed — total-only stacked charts render |
| 3 | `src/reportbuilder/api/routes_questions.py` | guard L854–869 (single-chart preview) | Raises `422` likewise | Guard removed |
| 4 | `src/reportbuilder/render/image/bars.py` | `_stacked_layout()` L367–388 | No-classifier case degrades to **one solid bar per category** (a plain bar chart, not a stack) | No-classifier case → **one "Total" bar** stacked by the answer categories |

**Why site 4 matters even though sites 1–3 are the "blockers":** removing the API guards alone would let the request through, but `_stacked_layout`'s `len(bars) <= 1` fallback would still render the *wrong* picture (one bar per answer option). The renderer fix is what makes the output correct. Verification must assert the *shape of the render*, not merely the absence of a 422.

**Out of scope (documented, not changed):** `src/reportbuilder/render/native/bar.py` (legacy pptx-native stacked builders — not used by the product's image render mode). The native path's category/segment transposition is pre-existing and unrelated; this plan neither relies on nor "fixes" it.

---

## Verification Taxonomy

| Layer | What it proves | Files | Backend |
|-------|----------------|-------|---------|
| **Unit** | `_stacked_layout` produces one "Total" bar + category stack, sums to 100% | `tests/rb/render/image/test_image_bars_line.py` | none |
| **Unit (schema)** | `stacked_schema` exposes `classifying_var` as **optional** | `tests/rb/api/test_chart_types.py` | none |
| **Integration (render)** | `compute()` → image builder yields exactly one PICTURE with the right stack | `tests/rb/render/image/test_stacked_total_only.py` (new) | none |
| **Integration (API)** | preview-chart & orchestrate-render return **200 PNG** (not 422) for a stacked chart with no classifier | `tests/rb/api/test_rx_backend.py`, `tests/rb/api/test_routes_render.py` | in-process `TestClient` + `Mock`/`FakeHive` |
| **e2e (synthetic)** | Full ingest→model→spec→render over synthetic SAV, soffice-free | `tests/rb/e2e/test_stacked_total_only_e2e.py` (new) | none |
| **e2e (real SAV, demo group)** | The three real client SAVs each render a total-only stacked bar via the **local-fs** demo API | `tests/rb/e2e/test_stacked_total_only_demo.py` (new, `@pytest.mark.demo`) | `NSIGHT_DEMO=1` `InMemoryDataHiveClient` |

---

## File Structure (created / modified)

**Production (fix — Phase C only):**
- Modify: `src/reportbuilder/render/config_schema.py` (`stacked_schema`)
- Modify: `src/reportbuilder/api/routes_render.py` (remove `_STACKED` guard)
- Modify: `src/reportbuilder/api/routes_questions.py` (remove preview guard)
- Modify: `src/reportbuilder/render/image/bars.py` (`_stacked_layout`)

**Tests & harness:**
- Modify: `pyproject.toml` (register `demo` marker)
- Create: `tests/rb/e2e/conftest.py` (demo-mode fixture: skip unless `NSIGHT_DEMO=1`, seed temp store)
- Modify: `.gitignore` (ignore `tests/rb/e2e/data/`)
- Create: `tests/rb/e2e/data/README.md` (how to populate SAV copies locally)
- Modify: `tests/rb/render/image/test_image_bars_line.py` (rewrite fallback test)
- Modify: `tests/rb/api/test_chart_types.py` (invert required→optional)
- Modify: `tests/rb/api/test_rx_backend.py` (invert two 422 tests → 200/not-blocked)
- Create: `tests/rb/render/image/test_stacked_total_only.py`
- Create: `tests/rb/e2e/test_stacked_total_only_e2e.py`
- Create: `tests/rb/e2e/test_stacked_total_only_demo.py`

---

# Execution Phases

Phases run in order. **Phase B (manifest/RED) must complete and be confirmed RED before Phase C (fix) begins.**

---

## Phase A — Harness prep & green baseline

Goal: register the demo test group, wire the local-fs fixture, stage the real SAVs into a gitignored location, and record a clean baseline so later RED/GREEN transitions are unambiguous.

### Task A1: Establish the pre-change baseline

**Files:** none (read-only)

- [ ] **Step 1: Run the full backend suite and record the result**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb -q 2>&1 | tail -30
```
Expected: a green (all-passing) summary, e.g. `NNN passed, M skipped`. Note the exact counts — they are the reference for Phase D. If anything is red *before* we start, stop and investigate; do not proceed on a dirty baseline.

- [ ] **Step 2: Confirm the four root-cause sites are as described**

Run:
```bash
cd /home/johan/Projects/nsight/proto
grep -n "classifying_var_field(required=True)" src/reportbuilder/render/config_schema.py
grep -n "_STACKED = {" src/reportbuilder/api/routes_render.py
grep -n "Stacked charts need a classifying" src/reportbuilder/api/routes_questions.py
grep -n "def _stacked_layout" src/reportbuilder/render/image/bars.py
```
Expected: one hit each (schema L~146, render guard L~84, questions guard L~866, layout L~367). If a location has drifted, update the line references in this plan before continuing.

### Task A2: Register the `demo` pytest marker

**Files:**
- Modify: `pyproject.toml` (`[tool.pytest.ini_options].markers`)

- [ ] **Step 1: Add the marker**

In `pyproject.toml`, extend the `markers` list:
```toml
markers = [
    "integration: touches the real Attendo files",
    "judge: live Claude-as-judge test, needs ANTHROPIC_API_KEY",
    "live: live egoHive smoke test, skipped when egoHive is unreachable",
    "demo: local-filesystem demo-mode e2e (NSIGHT_DEMO=1); auto-skips otherwise",
]
```

- [ ] **Step 2: Verify the marker is known**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest --markers 2>&1 | grep -A0 "@pytest.mark.demo"
```
Expected: a line describing `@pytest.mark.demo`. No `PytestUnknownMarkWarning` later.

### Task A3: Demo-mode e2e fixture (local-fs, skip-unless-demo)

**Files:**
- Create: `tests/rb/e2e/conftest.py`

**Interfaces:**
- Produces fixture `demo_client_app` → `(TestClient, case_id)` backed by `InMemoryDataHiveClient` rooted at a per-test temp dir; skips the test entirely unless `NSIGHT_DEMO=1`.
- Produces fixture `real_sav_paths` → `list[pathlib.Path]` of the three client SAVs (from `tests/rb/e2e/data/sav/`, falling back to `input/`); skips if none present.

- [ ] **Step 1: Write the conftest**

Create `tests/rb/e2e/conftest.py`:
```python
"""Fixtures for demo-mode (NSIGHT_DEMO=1) e2e tests — local filesystem store, no
live datahive. Tests using these fixtures auto-skip unless NSIGHT_DEMO=1.
"""
from __future__ import annotations

import os
import pathlib

import pytest
from fastapi.testclient import TestClient


# Filenames of the three current client SAVs (see tests/rb/e2e/data/README.md).
_SAV_FILENAMES = (
    "spss_FINAL_HolidayClub.sav",
    "spss AttendoSuomi-Brandiseuranta_112025.sav",
    "spss Synsam_segmenteillä_vainvalittu_segmmalli.sav",
)

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]  # e2e -> rb -> tests -> proto
_DATA_DIR = pathlib.Path(__file__).resolve().parent / "data" / "sav"
_INPUT_DIR = _REPO_ROOT / "input"


def _resolve_sav(name: str) -> pathlib.Path | None:
    """Prefer the gitignored test-data copy; fall back to the tracked input/ file."""
    for base in (_DATA_DIR, _INPUT_DIR):
        p = base / name
        if p.is_file():
            return p
    return None


@pytest.fixture
def real_sav_paths() -> list[pathlib.Path]:
    paths = [p for p in (_resolve_sav(n) for n in _SAV_FILENAMES) if p is not None]
    if not paths:
        pytest.skip(
            "No client SAVs found — copy them into tests/rb/e2e/data/sav/ "
            "(see README) or ensure input/ contains them."
        )
    return paths


@pytest.fixture
def demo_client_app(tmp_path, monkeypatch):
    """A TestClient backed by the local-fs InMemoryDataHiveClient (NSIGHT_DEMO path),
    rooted at a throwaway temp dir. Skips unless NSIGHT_DEMO=1 so the standard
    suite never runs it. Returns (client, case_id)."""
    if os.environ.get("NSIGHT_DEMO") != "1":
        pytest.skip("demo-group test — set NSIGHT_DEMO=1 to run")

    from reportbuilder.api.app import create_app
    from reportbuilder.store.memory_client import InMemoryDataHiveClient

    store_dir = tmp_path / "demo-store"
    store_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("NSIGHT_DEMO_DIR", str(store_dir))

    client = InMemoryDataHiveClient(storage_dir=str(store_dir))
    app = create_app(client=client)
    tc = TestClient(app)

    resp = tc.post("/cases", json={"name": "stacked-total-only-demo"})
    assert resp.status_code in (200, 201), resp.text
    case_id = resp.json()["id"] if "id" in resp.json() else resp.json().get("case_id")
    assert case_id, f"unexpected /cases response: {resp.json()!r}"
    return tc, case_id
```

> **Note for the implementer:** the `/cases` response key (`id` vs `case_id`) is read defensively above. Confirm the actual key with `grep -n "def create_case\|return" src/reportbuilder/api/routes_cases.py` and simplify if desired — do not leave the code broken if the key differs.

- [ ] **Step 2: Sanity-check the fixture imports (collection only)**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/e2e/ --collect-only -q 2>&1 | tail -15
```
Expected: collection succeeds (no import errors). Demo tests may show as deselected/skip candidates — that's fine.

### Task A4: Stage the real SAVs into a gitignored data dir

**Files:**
- Modify: `.gitignore`
- Create: `tests/rb/e2e/data/README.md`

- [ ] **Step 1: Ignore the e2e data dir**

Append to `.gitignore`:
```gitignore
# Local-only client SAV copies for demo-group e2e (IPR — never commit)
tests/rb/e2e/data/
```

- [ ] **Step 2: Document how to populate it**

Create `tests/rb/e2e/data/README.md`:
```markdown
# e2e SAV test data (local only — gitignored)

The demo-group e2e (`@pytest.mark.demo`) renders total-only stacked bars over the
three current client SAVs. These are **client IPR** and must never be committed;
this directory is gitignored.

Populate it locally from the tracked `input/` copies:

    mkdir -p tests/rb/e2e/data/sav
    cp "input/spss_FINAL_HolidayClub.sav" tests/rb/e2e/data/sav/
    cp "input/spss AttendoSuomi-Brandiseuranta_112025.sav" tests/rb/e2e/data/sav/
    cp "input/spss Synsam_segmenteillä_vainvalittu_segmmalli.sav" tests/rb/e2e/data/sav/

If absent, the demo-group tests skip cleanly. Run the group with:

    NSIGHT_DEMO=1 python -m pytest tests/rb/e2e -m demo -v
```

- [ ] **Step 3: Copy the SAVs locally**

Run:
```bash
cd /home/johan/Projects/nsight/proto
mkdir -p tests/rb/e2e/data/sav
cp "input/spss_FINAL_HolidayClub.sav" tests/rb/e2e/data/sav/
cp "input/spss AttendoSuomi-Brandiseuranta_112025.sav" tests/rb/e2e/data/sav/
cp "input/spss Synsam_segmenteillä_vainvalittu_segmmalli.sav" tests/rb/e2e/data/sav/
git status --short tests/rb/e2e/data/
```
Expected: three files present; `git status` shows **nothing** for that dir (gitignored). If they appear as untracked, the `.gitignore` entry is wrong — fix before proceeding.

- [ ] **Step 4: Commit the harness (no client data)**

```bash
cd /home/johan/Projects/nsight/proto
git add pyproject.toml .gitignore tests/rb/e2e/conftest.py tests/rb/e2e/data/README.md
git commit -m "test(harness): demo marker + local-fs e2e fixture + gitignored SAV data dir"
```

---

## Phase B — MANIFEST the defect (RED)

Goal: encode the *desired* behaviour at every layer and prove each test FAILS against unmodified production code. **No production `src/` edit happens in this phase.**

### Task B1: Unit — `_stacked_layout` total-only single bar (RED)

**Files:**
- Modify: `tests/rb/render/image/test_image_bars_line.py`

**Interfaces:**
- Consumes: `reportbuilder.render.image.bars._stacked_layout(series) -> (bars, stack, data)`.

- [ ] **Step 1: Replace the stale fallback test with the desired-behaviour test**

In `tests/rb/render/image/test_image_bars_line.py`, replace the whole `test_stacked_layout_without_classifier_falls_back` function (currently L245–262) with:
```python
def test_stacked_layout_without_classifier_single_total_bar():
    """No classifier (segments == ('Total',)) → ONE 'Total' bar whose stack is the
    question's answer categories; the single bar sums to 100% (the total-only
    distribution bar the user asked for)."""
    from reportbuilder.render.image.bars import _stacked_layout

    cells = {
        ("Yes", "Total"): Cell(pct=65.0, count=None, mean=None),
        ("No", "Total"): Cell(pct=35.0, count=None, mean=None),
    }
    s = SeriesResult(
        categories=("Yes", "No"),
        segments=("Total",),
        cells=cells,
        base_n={"Total": 100},
        statistic="pct",
    )
    bars, stack, data = _stacked_layout(s)
    assert list(bars) == ["Total"], "total-only render must be a single 'Total' bar"
    assert list(stack) == ["Yes", "No"], "stack members are the answer categories"
    # data is keyed by stack member; one value per bar.
    assert data["Yes"] == [65.0]
    assert data["No"] == [35.0]
    assert abs(sum(data[q][0] for q in stack) - 100.0) < 1e-6
```

- [ ] **Step 2: Run it — confirm RED**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/render/image/test_image_bars_line.py::test_stacked_layout_without_classifier_single_total_bar -v
```
Expected: **FAIL**. Against current code `_stacked_layout` returns `bars == ["Yes","No"]`, `stack == ["Total"]`, so `assert list(bars) == ["Total"]` fails. This proves the renderer defect.

### Task B2: Unit — schema exposes `classifying_var` as optional (RED)

**Files:**
- Modify: `tests/rb/api/test_chart_types.py`

- [ ] **Step 1: Invert the requirement assertion**

Replace `test_stacked_requires_classifying_var` (L52–56) with:
```python
def test_stacked_classifying_var_optional():
    """Stacked charts accept a classifying variable but no longer REQUIRE it — a
    total-only stacked distribution bar is valid. The field must be present and
    not flagged required."""
    cat = _catalog()
    for cid in ("stacked_vertical_bar", "stacked_horizontal_bar"):
        fld = next(f for f in cat[cid]["config"] if f["key"] == "classifying_var")
        assert fld.get("required") in (False, None), (
            f"{cid} classifying_var must be optional, got required={fld.get('required')!r}"
        )
```
> Confirm the catalog accessor name (`_catalog()` / `cat[...]`) matches the rest of the file; reuse whatever `test_stacked_requires_classifying_var` used (it referenced `cat[cid]["config"]`).

- [ ] **Step 2: Run it — confirm RED**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/api/test_chart_types.py::test_stacked_classifying_var_optional -v
```
Expected: **FAIL** — current schema emits `required: true`, so `in (False, None)` fails.

### Task B3: Integration (API) — preview-chart & render no longer blocked (RED)

**Files:**
- Modify: `tests/rb/api/test_rx_backend.py`

- [ ] **Step 1: Replace the two 422 guard tests with "not blocked" tests**

Replace `test_preview_chart_stacked_vertical_without_classifying_var_returns_422` and `test_preview_chart_stacked_horizontal_without_classifying_var_returns_422` (L247–291) with:
```python
def _assert_stacked_no_dim_not_blocked(spec: dict) -> None:
    """A stacked chart with no classifying_var must NOT be rejected with a
    'classifying variable' 422. When soffice is available it renders a 200 PNG;
    otherwise we at least assert the guard is gone (status != 422)."""
    sav_bytes = synthetic_sav_bytes()
    mock_client = Mock()
    mock_client.get_material.return_value = sav_bytes
    app = create_app(client=mock_client)
    tc = TestClient(app)

    response = tc.post("/materials/mat-rx2/preview-chart", json=spec)

    assert response.status_code != 422 or "classifying variable" not in (
        response.json().get("detail", "").lower()
    ), (
        "stacked chart without classifying_var must no longer be blocked; "
        f"got {response.status_code}: {response.text[:300]}"
    )

    soffice_present = (
        shutil.which("soffice") is not None or shutil.which("libreoffice") is not None
    )
    if soffice_present:
        assert response.status_code == 200, (
            f"expected 200 PNG for total-only stacked chart, got "
            f"{response.status_code}: {response.text[:300]}"
        )
        assert response.headers["content-type"].startswith("image/png")
        assert response.content[:4] == b"\x89PNG"


def test_preview_chart_stacked_vertical_without_classifying_var_not_blocked() -> None:
    """stacked_vertical_bar with no classifying_var → total-only distribution bar,
    not a 422. (defect: stacked bars can use just the total)"""
    _assert_stacked_no_dim_not_blocked(_STACKED_VERT_NO_DIM_SPEC)


def test_preview_chart_stacked_horizontal_without_classifying_var_not_blocked() -> None:
    """stacked_horizontal_bar with no classifying_var → total-only distribution bar,
    not a 422."""
    _assert_stacked_no_dim_not_blocked(_STACKED_HORIZ_NO_DIM_SPEC)
```
(The `_STACKED_VERT_NO_DIM_SPEC` / `_STACKED_HORIZ_NO_DIM_SPEC` fixtures at L178–190 stay as-is. `shutil` and `Mock`/`create_app`/`TestClient`/`synthetic_sav_bytes` are already imported in this file.)

- [ ] **Step 2: Run them — confirm RED**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/api/test_rx_backend.py -k "not_blocked" -v
```
Expected: **FAIL** for both. The guard at `routes_questions.py:857` returns `422` with detail containing "classifying variable" *before* any render, so the `status_code != 422 or ...` assertion fails regardless of soffice. This proves the preview-route blocker.

### Task B4: Integration (render) — compute()→image builder shape (RED)

**Files:**
- Create: `tests/rb/render/image/test_stacked_total_only.py`

**Interfaces:**
- Consumes: `reportbuilder.stats.engine.compute`, `reportbuilder.render.image.IMAGE_BUILDERS`, `reportbuilder.render.image.bars._stacked_layout`, `RenderContext`.

- [ ] **Step 1: Write the render integration test**

Create `tests/rb/render/image/test_stacked_total_only.py`:
```python
"""Total-only stacked bar: a single-question distribution (no classifying_var)
renders as ONE 100%-stacked bar whose stack is the answer categories.

Covers the render-path half of the 'stacked bars can use just the total' defect:
the API guards are irrelevant here — this drives compute() and the image builder
directly, so it fails on the _stacked_layout fallback until that is fixed.
"""
from __future__ import annotations

import io

import pytest
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE_TYPE
from pptx.util import Inches

from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.render.base import RenderContext, Slot, StyleSpec
from reportbuilder.render.image import IMAGE_BUILDERS
from reportbuilder.render.image.bars import _stacked_layout
from reportbuilder.stats.engine import compute
from reportbuilder.stats.series import Cell, SeriesResult


def _spec(chart_type: str) -> ChartSpec:
    return ChartSpec(
        question_ref="q1", chart_type=chart_type, statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="slot1",
        elements=ElementToggles(title=True, legend=True, data_labels=True),
    )


def _total_only_series() -> SeriesResult:
    """A 4-level Likert distribution with only a 'Total' segment (no classifier)."""
    cats = ("Strongly disagree", "Disagree", "Agree", "Strongly agree")
    pcts = (10.0, 20.0, 45.0, 25.0)
    cells = {(c, "Total"): Cell(pct=p, count=None, mean=None) for c, p in zip(cats, pcts)}
    return SeriesResult(categories=cats, segments=("Total",), cells=cells,
                        base_n={"Total": 200}, statistic="pct")


@pytest.mark.parametrize("chart_type", ["stacked_vertical_bar", "stacked_horizontal_bar"])
def test_total_only_layout_is_single_bar(chart_type):
    bars, stack, data = _stacked_layout(_total_only_series())
    assert list(bars) == ["Total"]
    assert len(stack) == 4
    assert abs(sum(data[c][0] for c in stack) - 100.0) < 1e-6


@pytest.mark.parametrize("chart_type", ["stacked_vertical_bar", "stacked_horizontal_bar"])
def test_total_only_renders_one_picture(chart_type):
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    slot = Slot(slide_index=0, left=Inches(1), top=Inches(1),
                width=Inches(8), height=Inches(5), name="slot1")
    ctx = RenderContext(slide=slide, slot=slot, style=StyleSpec(),
                        spec=_spec(chart_type), series=_total_only_series(),
                        fmt=NumberFormat())
    IMAGE_BUILDERS[chart_type](ctx)
    pics = [s for s in slide.shapes if s.shape_type == MSO_SHAPE_TYPE.PICTURE]
    assert len(pics) == 1, f"expected exactly one chart picture, found {len(pics)}"
    assert pics[0].image.blob[:4] == b"\x89PNG"
```

- [ ] **Step 2: Run it — confirm RED**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/render/image/test_stacked_total_only.py -v
```
Expected: `test_total_only_layout_is_single_bar` **FAILS** (`bars == ["Strongly disagree", ...]`, not `["Total"]`). The `_renders_one_picture` cases may pass (the fallback still draws *a* picture) — that's acceptable; the layout test is the manifest. Record which fail.

### Task B5: e2e (synthetic, soffice-free) — full ingest→render (RED)

**Files:**
- Create: `tests/rb/e2e/test_stacked_total_only_e2e.py`

**Interfaces:**
- Consumes: `reportbuilder.ingest.sav_reader.read_sav`, `reportbuilder.ingest.multi_group.enrich_model`, `compute`, `_stacked_layout`, `synthetic_sav` fixture.

- [ ] **Step 1: Write the synthetic e2e**

Create `tests/rb/e2e/test_stacked_total_only_e2e.py`:
```python
"""e2e (soffice-free): a synthetic SAV's single-choice question, charted as a
stacked bar with NO classifying variable, renders one total-only 100% bar.

This walks the real product path minus rasterisation: read_sav -> enrich_model ->
compute -> image _stacked_layout. It fails until _stacked_layout treats the
no-classifier case as a single 'Total' bar.
"""
from __future__ import annotations

import pytest

from reportbuilder.ingest.multi_group import enrich_model
from reportbuilder.ingest.sav_reader import read_sav
from reportbuilder.model.report import (
    ChartSpec, ElementToggles, NumberFormat, SortSpec,
)
from reportbuilder.render.image.bars import _stacked_layout
from reportbuilder.stats.engine import compute
from reportbuilder.testing.fixtures import synthetic_sav


def _pick_distribution_question(model):
    """First single-choice question whose primary variable has >=2 non-missing
    value labels — a real answer distribution to stack to 100%."""
    for q in model.questions:
        if q.kind != "single":
            continue
        var = model.variables[q.variables[0]]
        labels = [vl for vl in var.value_labels if vl.value not in var.missing_values]
        if len(labels) >= 2:
            return q
    return None


@pytest.mark.parametrize("chart_type", ["stacked_vertical_bar", "stacked_horizontal_bar"])
def test_synthetic_total_only_stacked(tmp_path, chart_type):
    path = synthetic_sav(tmp_path)
    df, model = read_sav(path)
    model = enrich_model(model)
    q = _pick_distribution_question(model)
    assert q is not None, "synthetic SAV should contain a single-choice question"

    spec = ChartSpec(
        question_ref=q.qid, chart_type=chart_type, statistic="pct",
        classifying_var=None, number_format=NumberFormat(),
        sort=SortSpec(basis="data_order"), template_slot="slot1",
        elements=ElementToggles(title=True, legend=True, data_labels=True),
    )
    series = compute(q, spec, df, model)
    assert series.segments == ("Total",), "no classifier => single Total segment"

    bars, stack, data = _stacked_layout(series)
    assert list(bars) == ["Total"], "total-only stacked bar is a single 'Total' bar"
    assert len(stack) >= 2, "stack members are the answer categories"
    assert abs(sum(data[c][0] for c in stack) - 100.0) < 1e-6
```

- [ ] **Step 2: Run it — confirm RED**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/e2e/test_stacked_total_only_e2e.py -v
```
Expected: **FAIL** at `assert list(bars) == ["Total"]` (current fallback returns one bar per category).

### Task B6: e2e (real SAV, demo group) — three client files via local-fs API (RED)

**Files:**
- Create: `tests/rb/e2e/test_stacked_total_only_demo.py`

**Interfaces:**
- Consumes fixtures `demo_client_app` and `real_sav_paths` from `tests/rb/e2e/conftest.py`; the `/cases/{case_id}/materials` upload route, `GET /materials/{id}/questions`, and `POST /materials/{id}/preview-chart`.

- [ ] **Step 1: Write the demo-group e2e**

Create `tests/rb/e2e/test_stacked_total_only_demo.py`:
```python
"""Demo-group e2e (@pytest.mark.demo, NSIGHT_DEMO=1, local filesystem store):
each of the three current client SAVs must render a total-only stacked bar
(stacked_horizontal_bar, no classifying_var) as a 200 PNG through the real API.

Run with:  NSIGHT_DEMO=1 python -m pytest tests/rb/e2e -m demo -v
Auto-skips when NSIGHT_DEMO != 1 or the SAV copies are absent.
"""
from __future__ import annotations

import shutil

import pytest

pytestmark = pytest.mark.demo


def _pick_distribution_qid(questions: list[dict]) -> str | None:
    """First chartable single-choice question with >=2 answer values."""
    for q in questions:
        if not q.get("chartable"):
            continue
        if q.get("kind") != "single":
            continue
        if len(q.get("values") or []) >= 2:
            return q["qid"]
    return None


def _upload(tc, case_id, sav_path):
    with open(sav_path, "rb") as fh:
        resp = tc.post(
            f"/cases/{case_id}/materials",
            files={"file": (sav_path.name, fh, "application/octet-stream")},
        )
    assert resp.status_code in (200, 201), f"{sav_path.name}: {resp.text[:300]}"
    return resp.json()["material_id"]


def test_real_savs_render_total_only_stacked(demo_client_app, real_sav_paths):
    tc, case_id = demo_client_app
    soffice = shutil.which("soffice") or shutil.which("libreoffice")

    for sav_path in real_sav_paths:
        material_id = _upload(tc, case_id, sav_path)

        qresp = tc.get(f"/materials/{material_id}/questions")
        assert qresp.status_code == 200, qresp.text
        qid = _pick_distribution_qid(qresp.json()["questions"])
        assert qid, f"{sav_path.name}: no single-choice distribution question found"

        spec = {
            "question_ref": qid,
            "chart_type": "stacked_horizontal_bar",
            "statistic": "pct",
            # classifying_var intentionally omitted — the total-only case
        }
        presp = tc.post(f"/materials/{material_id}/preview-chart", json=spec)

        # The guard must be gone: never a 'classifying variable' 422.
        assert not (
            presp.status_code == 422
            and "classifying variable" in presp.json().get("detail", "").lower()
        ), f"{sav_path.name}/{qid}: still blocked -> {presp.text[:300]}"

        if soffice:
            assert presp.status_code == 200, (
                f"{sav_path.name}/{qid}: expected 200 PNG, got "
                f"{presp.status_code}: {presp.text[:300]}"
            )
            assert presp.headers["content-type"].startswith("image/png")
            assert presp.content[:4] == b"\x89PNG"
```

- [ ] **Step 2: Confirm it SKIPS without demo mode**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/e2e/test_stacked_total_only_demo.py -v
```
Expected: **SKIPPED** ("demo-group test — set NSIGHT_DEMO=1 to run"). This proves the group isolation (standard suite never runs it).

- [ ] **Step 3: Run the demo group — confirm RED**

Run:
```bash
cd /home/johan/Projects/nsight/proto
NSIGHT_DEMO=1 python -m pytest tests/rb/e2e/test_stacked_total_only_demo.py -m demo -v
```
Expected: **FAIL** — the preview-chart guard returns a `classifying variable` 422 for every SAV, tripping the `assert not (... 422 ...)`. This proves the blocker on real client data via the local-fs path. (If the SAV copies are missing it will SKIP instead — populate `tests/rb/e2e/data/sav/` per Task A4 first.)

### Task B7: Consolidated RED checkpoint

**Files:** none

- [ ] **Step 1: Run every manifest test together and confirm the expected failures**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest \
  tests/rb/render/image/test_image_bars_line.py::test_stacked_layout_without_classifier_single_total_bar \
  tests/rb/api/test_chart_types.py::test_stacked_classifying_var_optional \
  tests/rb/api/test_rx_backend.py -k "not_blocked" \
  tests/rb/render/image/test_stacked_total_only.py \
  tests/rb/e2e/test_stacked_total_only_e2e.py \
  -v
```
Expected: a batch of **FAILs** covering B1, B2, B3, B4(layout), B5. Nothing green among the manifest assertions. **Do not proceed to Phase C until this is confirmed.**

- [ ] **Step 2: Commit the RED tests**

```bash
cd /home/johan/Projects/nsight/proto
git add tests/rb/render/image/test_image_bars_line.py tests/rb/api/test_chart_types.py \
        tests/rb/api/test_rx_backend.py tests/rb/render/image/test_stacked_total_only.py \
        tests/rb/e2e/test_stacked_total_only_e2e.py tests/rb/e2e/test_stacked_total_only_demo.py
git commit -m "test(stacked): manifest total-only stacked bar defect (RED)"
```

---

## Phase C — FIX (drive to GREEN)

Goal: apply the four production changes. Each task ends by running its manifest test and confirming GREEN.

### Task C1: Renderer — `_stacked_layout` single "Total" bar

**Files:**
- Modify: `src/reportbuilder/render/image/bars.py` (`_stacked_layout`, L367–388)

- [ ] **Step 1: Replace the function body**

Replace `_stacked_layout` (L367–388) with:
```python
def _stacked_layout(series):
    """Decompose a segmented series into a clean 100%-stacked layout.

    A stacked bar compares composition: each BAR is a classifying-variable
    segment and the STACK is the question's answer categories. The engine's
    per-segment percentages sum to 100 within a segment (column %), so each bar
    fills exactly 100% — no overshoot, no floating 'Total'. Returns
    (bars, stack, data) where data[stack_member] = [value per bar].

    With no classifier (segments == ('Total',)) there is nothing to split by, so
    the single 'Total' column IS the one bar and the answer categories become its
    stack — the classic single 100%-stacked distribution bar (the "just total"
    case).
    """
    cats, segs, data = series_values(series)
    bars = [s for s in segs if s != "Total"]
    if not bars:
        # No classifier: one 'Total' bar, stacked by the answer categories.
        bars = ["Total"]
    stack = cats
    new_data = {
        qcat: [data[seg][ci] for seg in bars] for ci, qcat in enumerate(cats)
    }
    return bars, stack, new_data
```

- [ ] **Step 2: Run the renderer manifests — confirm GREEN**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest \
  tests/rb/render/image/test_image_bars_line.py::test_stacked_layout_without_classifier_single_total_bar \
  tests/rb/render/image/test_stacked_total_only.py \
  tests/rb/e2e/test_stacked_total_only_e2e.py -v
```
Expected: all **PASS**. Also re-run the pre-existing transpose test to guard against regression:
```bash
python -m pytest tests/rb/render/image/test_image_bars_line.py::test_stacked_layout_excludes_total_and_transposes -v
```
Expected: **PASS** (multi-segment path unchanged).

### Task C2: Schema — make `classifying_var` optional for stacked

**Files:**
- Modify: `src/reportbuilder/render/config_schema.py` (`stacked_schema`, L144–146)

- [ ] **Step 1: Relax the schema**

Replace `stacked_schema` (L144–146) with:
```python
def stacked_schema() -> tuple[ConfigField, ...]:
    """Stacked charts: the classifying variable is OPTIONAL. With one, each bar is
    a group split by the shared answer categories; without one, the chart is a
    single 100%-stacked bar of the question's answer distribution (the 'total')."""
    return (statistic_field(), classifying_var_field(), *_common_tail())
```

- [ ] **Step 2: Run the schema manifest — confirm GREEN**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/api/test_chart_types.py -v
```
Expected: `test_stacked_classifying_var_optional` **PASS**; `test_multi_series_types_expose_classifying_var` and `test_single_series_types_hide_classifying_var` still **PASS** (stacked still exposes the field; pie/doughnut/funnel still omit it).

### Task C3: Remove the full-deck render guard

**Files:**
- Modify: `src/reportbuilder/api/routes_render.py` (delete `_STACKED` guard, L81–98)

- [ ] **Step 1: Delete the guard block**

Remove the entire block (currently L81–98) beginning with the comment `# Guard (RX-be.3): a stacked single/multi chart needs a classifying variable` and ending with the closing `)` of the `raise HTTPException(...)`. Leave the surrounding code (`model = enrich_model(model)` above; the `# 3. Build the PPTX deck...` comment below) intact.

- [ ] **Step 2: Verify the module imports & nothing else referenced `_STACKED`**

Run:
```bash
cd /home/johan/Projects/nsight/proto
grep -n "_STACKED" src/reportbuilder/api/routes_render.py || echo "no _STACKED refs (good)"
python -c "import reportbuilder.api.routes_render"
```
Expected: `no _STACKED refs (good)` and a clean import (no error).

### Task C4: Remove the preview-chart guard

**Files:**
- Modify: `src/reportbuilder/api/routes_questions.py` (delete guard, L854–869)

- [ ] **Step 1: Delete the guard block**

Remove the block (currently L854–869) beginning `# Guard (RX-be.3): a stacked single/multi chart needs a classifying variable` and ending at the closing `)` of its `raise HTTPException(...)`. Leave `model = enrich_model(model)` above and `# 2. Convert request body to ChartSpec` below intact.

- [ ] **Step 2: Run the API manifests — confirm GREEN**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -c "import reportbuilder.api.routes_questions"
python -m pytest tests/rb/api/test_rx_backend.py -k "not_blocked" -v
```
Expected: both `not_blocked` tests **PASS**. Without soffice they pass on the `!= 422` assertion; with soffice they additionally assert the 200 PNG.

### Task C5: Fix-phase commit

- [ ] **Step 1: Commit the fix**

```bash
cd /home/johan/Projects/nsight/proto
git add src/reportbuilder/render/image/bars.py src/reportbuilder/render/config_schema.py \
        src/reportbuilder/api/routes_render.py src/reportbuilder/api/routes_questions.py
git commit -m "fix(charts): allow total-only stacked bars (no classifying variable required)"
```

---

## Phase D — RE-TEST: regression & real-data e2e

Goal: prove the fix is complete, nothing regressed, and the real client SAVs render via the local-fs path.

### Task D1: Full manifest suite GREEN

**Files:** none

- [ ] **Step 1: Re-run the consolidated manifest batch**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest \
  tests/rb/render/image/test_image_bars_line.py::test_stacked_layout_without_classifier_single_total_bar \
  tests/rb/api/test_chart_types.py::test_stacked_classifying_var_optional \
  tests/rb/api/test_rx_backend.py -k "not_blocked" \
  tests/rb/render/image/test_stacked_total_only.py \
  tests/rb/e2e/test_stacked_total_only_e2e.py -v
```
Expected: **all PASS**.

### Task D2: Targeted regression — render, stats, API

**Files:** none

- [ ] **Step 1: Re-run the render, stats, and API suites**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/render tests/rb/stats tests/rb/api -q 2>&1 | tail -25
```
Expected: green. Pay special attention to: `test_image_bars_line.py` (stacked transpose + orientation), `test_chart_types.py`, `test_rx_backend.py`, and any battery-stacked tests (batteries must still render — their path is unchanged but shares `_stacked_layout`).

### Task D3: Full backend suite vs. baseline

**Files:** none

- [ ] **Step 1: Run the whole suite**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb -q 2>&1 | tail -15
```
Expected: green, with pass count = **Task A1 baseline** count adjusted only by the tests this plan added/renamed (net: +`test_stacked_total_only.py` cases, +`test_stacked_total_only_e2e.py` cases, renamed fallback/schema/rx tests). No unexplained failures or new skips.

### Task D4: Demo group over the three real SAVs (local-fs)

**Files:** none

- [ ] **Step 1: Ensure SAV copies exist** (from Task A4 Step 3). If skipped earlier, run that copy command now.

- [ ] **Step 2: Run the demo group**

Run:
```bash
cd /home/johan/Projects/nsight/proto
NSIGHT_DEMO=1 python -m pytest tests/rb/e2e -m demo -v
```
Expected: `test_real_savs_render_total_only_stacked` **PASS** (uploads each of the three client SAVs into a throwaway local-fs store, finds a single-choice question, and renders a total-only `stacked_horizontal_bar`). With LibreOffice present it asserts a 200 PNG per file; without it, it asserts the guard is gone. If SAVs are absent it SKIPS — in that case the fix is unverified on real data, so populate the data dir and re-run.

- [ ] **Step 3: Confirm the demo group stays isolated from the standard suite**

Run:
```bash
cd /home/johan/Projects/nsight/proto
python -m pytest tests/rb/e2e -q 2>&1 | tail -10
```
Expected: the demo test **SKIPS** (no `NSIGHT_DEMO`), synthetic e2e passes. Proves the group separation the requirement asks for.

### Task D5: Optional manual smoke (local server, image mode)

**Files:** none. Only if a human wants an eyeball check; not required for sign-off.

- [ ] **Step 1: Start the local demo server and render a total-only stacked bar**

Run (in a scratch terminal; suggest the user runs it via `!` if interactive login/长-running):
```bash
cd /home/johan/Projects/nsight/proto
NSIGHT_DEMO=1 NSIGHT_PORT=8200 python -m reportbuilder.api.server &
# then, against an already-uploaded material_id in work/demo-store:
curl -s -X POST localhost:8200/materials/<material_id>/preview-chart \
  -H 'content-type: application/json' \
  -d '{"question_ref":"<qid>","chart_type":"stacked_horizontal_bar","statistic":"pct"}' \
  -o /tmp/claude-1000/-home-johan-Projects-nsight-proto/5b3aa7fd-da72-487a-b19d-6c7db96898b6/scratchpad/stacked_total.png
file .../stacked_total.png
```
Expected: a PNG file (not a JSON 422). Visual check: one bar, stacked by answer categories, filling 100%. Kill the server afterward.

### Task D6: Final sign-off

- [ ] **Step 1: Confirm the checklist**
  - [ ] Phase A baseline recorded; harness (marker, fixture, gitignore) committed.
  - [ ] Every manifest test was observed RED in Phase B before any `src/` edit.
  - [ ] All four production sites changed (C1–C4).
  - [ ] All manifests GREEN (D1); render/stats/api regression green (D2); full suite green vs baseline (D3).
  - [ ] Demo group green on all three real SAVs via local-fs (D4); demo group skips in standard suite (D4 Step 3).
  - [ ] No client SAV staged for commit (`git status` clean under `tests/rb/e2e/data/`).
  - [ ] Nothing ran against staging or a live backend.

---

## Self-Review

**Spec coverage:**
- "Stacked horizontal and vertical bars … can be done using just total" → sites 1–4 fixed (C1–C4); asserted at unit (B1/B4), integration (B2/B3), and e2e (B5/B6) layers, both `stacked_vertical_bar` and `stacked_horizontal_bar` parametrised.
- "deep and extensive … unit, integration and e2e" → taxonomy table + Phases B/D cover all three; e2e includes synthetic (soffice-free) and real-SAV (demo) variants.
- "e2e based on current three SAV files … copy to test directories" → Task A4 copies the three `input/` SAVs into gitignored `tests/rb/e2e/data/sav/`; B6/D4 render each.
- "manifest the defect first … only after manifestation fix and re-test" → Phase B (RED, with explicit "confirm FAIL" steps and a B7 gate) strictly precedes Phase C (fix); Phase D re-tests.
- "verification never in staging … locally" → Global Constraints + every command is local; no deploy step exists.
- "applicable tests separated to own group when NSIGHT_DEMO=1 (local fs instead of datahive)" → `@pytest.mark.demo` + `demo_client_app` fixture (InMemoryDataHiveClient, skip-unless-`NSIGHT_DEMO=1`); D4 Step 3 proves isolation.

**Placeholder scan:** No TBD/TODO; every test and fix step contains full code; two "confirm the response key / accessor name" notes point at exact `grep` commands rather than leaving logic undefined.

**Type/name consistency:** `_stacked_layout` returns `(bars, stack, data)` used identically across B1/B4/B5/C1; `stacked_schema()`/`classifying_var_field()` names match `config_schema.py`; fixture names `demo_client_app`/`real_sav_paths` are defined in A3 and consumed in B6/D4; `IMAGE_BUILDERS` keys (`stacked_vertical_bar`, `stacked_horizontal_bar`) match the plugin registry.

---

**Plan complete.** Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

Which approach?
