# Preview Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the three uncoordinated systems that produce a slide preview
(template resolution, AI generation, rasterisation) with one resolved template,
one queue, and one sequential producer function — and land the two open tickets
that are the same work.

**Architecture:** The backend resolves a template once per file — style, fonts
and type sizes together — and caches that, so no per-slide work is left to cache.
The frontend gets a single module-level queue:
each slide runs one sequential function over an ordered producer registry, and
every producer decides whether it is needed by comparing a fingerprint of its
inputs against the fingerprint stored with its last output. The image
fingerprint works by exclusion, so new chart fields invalidate previews without
anyone remembering to add them.

**Tech Stack:** Python 3 / FastAPI / python-pptx / matplotlib (backend, `uv run
pytest`); React + TypeScript + Vite + TanStack Query (frontend); vitest for pure
modules (added by Task 5); Playwright for end-to-end verification.

**Spec:** `docs/superpowers/specs/2026-08-23-preview-pipeline-design.md`

## Global Constraints

- Backend tests run with `uv run pytest tests/suite tests/rb -q -m "not judge and not integration" --ignore=tests/suite/integration/api/test_oidc_failure_modes.py`.
- Frontend builds with `npm run build` in `web/`; it must stay clean.
- Never fail a render over styling: every new resolution path keeps the existing
  `except Exception` fallbacks, which exist so a bad template shows a plain
  chart rather than an error.
- The Design preview and the Preview step show the **same** image. One `chart`
  producer, one image per slide.
- `titleDataKey` (`web/src/lib/charts.ts:109`) is an **allow-list** and only
  gains a field if that field changes what the data *says*. The image
  fingerprint is a **deny-list**.
- The image fingerprint's deny-list is exactly: `slide_id`, `compare_group`,
  `slide_title_key`, `template_slot`, `excluded`.
- Work happens on branch `preview-pipeline`, not master.

---

### Task 1: Resolve the whole template once

**Files:**
- Create: `src/reportbuilder/render/template_cache.py`
- Modify: `src/reportbuilder/render/image/slide_chrome.py:500-516,715-719`
- Modify: `src/reportbuilder/api/routes_questions.py:31,1407,1463`
- Modify: `src/reportbuilder/api/routes_render.py:170-171`
- Test: `tests/suite/unit/render/test_template_cache.py`

**Interfaces:**
- Produces: `reportbuilder.render.template_cache.resolve(template_path: str) -> ResolvedTemplate`
  with `.style: TemplateStyleSpec` and `.spec: TemplateSpec`. Callers that today
  do `load_style_spec(path)` use `resolve(path).style`, and the resolved spec
  travels on the style as `style.resolved_spec` so everything already holding a
  style can read it without a new argument.

Two costs are being removed, not cached. `load_style_spec` opens the `.pptx`,
walks every layout via `inspect_template` and harvests via `extract_profile` —
per slide. And `slide_chrome.py` calls `build_spec` per slide at three sites
(`:504`, `:513`, `:717`), each passing a font derived per slide from the title
placeholder's chain, which re-loads a TTF through PIL inside
`size_for_cap_height`. Every chart slide is built from the same layout
(`style.chart_layout_index`), so that font is a property of the template: resolve
it once, build the spec once, and the three call sites become reads.

- [ ] **Step 1: Write the failing test**

```python
"""The template is resolved once per file, not once per slide."""
from __future__ import annotations

import shutil

from reportbuilder.render import template_cache


def test_resolve_returns_the_same_object_for_the_same_file(tmp_path):
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(), src)
    assert template_cache.resolve(str(src)) is template_cache.resolve(str(src))


def test_resolve_re_reads_a_changed_file(tmp_path):
    """A re-uploaded template must not keep serving the old resolution."""
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(), src)
    first = template_cache.resolve(str(src))
    shutil.copy(_another_template(), src)
    assert template_cache.resolve(str(src)) is not first


def test_style_matches_load_style_spec(tmp_path):
    from reportbuilder.render.style_spec import load_style_spec
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(), src)
    assert template_cache.resolve(str(src)).style.chart_layout_index == \
        load_style_spec(str(src)).chart_layout_index


def test_the_spec_is_built_once_and_carries_a_title_size(tmp_path):
    """The whole point: sizes are decided per TEMPLATE, before any slide."""
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(), src)
    spec = template_cache.resolve(str(src)).spec
    assert spec.title.size_pt > 0
    assert spec.subtitle.size_pt > 0
    assert spec.background


def test_the_spec_travels_with_the_style(tmp_path):
    """slide_chrome holds a style, not a ResolvedTemplate, and must still read it."""
    src = tmp_path / "t.pptx"
    shutil.copy(_a_template(), src)
    r = template_cache.resolve(str(src))
    assert r.style.resolved_spec is r.spec
```

Add the two helpers at the top, using templates the suite already ships:

```python
import pathlib

def _a_template() -> str:
    return str(pathlib.Path(__file__).parents[3] / "fixtures" / "templates" / "basic.pptx")

def _another_template() -> str:
    return str(pathlib.Path(__file__).parents[3] / "fixtures" / "templates" / "other.pptx")
```

If those files do not exist, find what the render tests already use with
`grep -rn "\.pptx" tests/suite/unit/render/ | head` and pick two that differ.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/suite/unit/render/test_template_cache.py -q`
Expected: FAIL — `ModuleNotFoundError: reportbuilder.render.template_cache`.

- [ ] **Step 3: Write the module**

```python
"""A template, resolved once.

Every preview and every deck slide needs the same answers about a template —
where its chart goes, what its palette is, what its headline looks like — and
each answer used to cost a full `.pptx` parse plus a font measurement, per
slide. A 60-slide deck paid for all of it 60 times.

Resolution is a pure function of the file's bytes, so it is cached on identity:
path plus size plus mtime. A re-uploaded template is a different file by that
key and re-resolves on its own; nothing has to remember to invalidate.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from reportbuilder.render.resolved_style import TemplateSpec, build_spec
from reportbuilder.render.style_spec import TemplateStyleSpec, load_style_spec


@dataclass(frozen=True)
class ResolvedTemplate:
    """Everything a render needs to know about a template."""

    style: TemplateStyleSpec
    spec: TemplateSpec


def _layout_title_font(template_path: str, layout_index: int) -> str:
    """The face this template gives a slide headline.

    `slide_chrome` used to ask this per slide, off the slide's own placeholder.
    Every chart slide is built from the same layout, so the answer is a property
    of the template and is settled here, once, before any slide exists.
    """
    try:
        from pptx import Presentation

        from reportbuilder.render.image.fast_preview import (
            _inherited_placeholder_style,
        )
        layout = Presentation(template_path).slide_layouts[layout_index]
        for ph in layout.placeholders:
            if ph.placeholder_format.type in (13, 1):  # CENTER_TITLE, TITLE
                return _inherited_placeholder_style(ph)[0]
    except Exception:  # noqa: BLE001 — styling must never break a render
        pass
    return ""


@lru_cache(maxsize=16)
def _resolve(path: str, size: int, mtime_ns: int) -> ResolvedTemplate:
    # size/mtime_ns are not read: they are the cache identity. A file whose
    # bytes changed has a different key and lands here again.
    style = load_style_spec(path)
    spec = build_spec(style, title_font=_layout_title_font(path, style.chart_layout_index))
    # slide_chrome and the compositor are handed a style, not a ResolvedTemplate,
    # and there are many such call sites. Letting the spec travel with the style
    # is what turns their per-slide build_spec calls into reads.
    style.resolved_spec = spec
    return ResolvedTemplate(style=style, spec=spec)


def resolve(template_path: str) -> ResolvedTemplate:
    """The resolved template at *template_path*, computed once per file.

    Concurrent first callers may both compute it — FastAPI runs sync endpoints in
    a threadpool. That is harmless: the result is a value, not a resource.
    """
    st = os.stat(template_path)
    return _resolve(template_path, st.st_size, st.st_mtime_ns)
```

Add the attribute to `TemplateStyleSpec` in
`src/reportbuilder/render/style_spec.py` so it is declared rather than grafted
on — default `None`, since a style can still be built without a template:

```python
    resolved_spec = None  # set by template_cache.resolve; see its docstring
```

- [ ] **Step 4: Run the test — it should pass**

Run: `uv run pytest tests/suite/unit/render/test_template_cache.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Make slide_chrome read the spec instead of rebuilding it**

Replace the bodies of `_spec_title_pt` and `_spec_subtitle_pt`
(`slide_chrome.py:500-516`) so they read what the template already resolved,
keeping their signatures — callers pass a font that is now only a fallback:

```python
def _spec_title_pt(style, font: str) -> float:
    """The title size this template's spec states, or 0.0 if it cannot say."""
    spec = getattr(style, "resolved_spec", None)
    if spec is not None:
        return spec.title.size_pt
    # No resolved template (a style built without one): fall back to measuring.
    try:
        from reportbuilder.render.resolved_style import build_spec
        return build_spec(style, title_font=font).title.size_pt
    except Exception:  # noqa: BLE001 — never fail a render over a font metric
        return 0.0


def _spec_subtitle_pt(style, font: str) -> float:
    """The subtitle size this template's spec states, or 0.0."""
    spec = getattr(style, "resolved_spec", None)
    if spec is not None:
        return spec.subtitle.size_pt
    try:
        from reportbuilder.render.resolved_style import build_spec
        return build_spec(style, subtitle_font=font).subtitle.size_pt
    except Exception:  # noqa: BLE001
        return 0.0
```

And at `slide_chrome.py:715-719`, use the resolved spec first:

```python
        spec = getattr(style, "resolved_spec", None) if style else None
        if spec is None and style is not None:
            from reportbuilder.render.resolved_style import build_spec
            spec = build_spec(style, title_font=_inherited_title_font(ph))
```

leaving the `if spec is not None and spec.title.size_pt:` block below unchanged.

- [ ] **Step 6: Route the three callers through resolve()**

In `src/reportbuilder/api/routes_questions.py`, change the import at line 31 from

```python
from reportbuilder.render.style_spec import load_style_spec as _load_style_spec
```

to

```python
from reportbuilder.render.template_cache import resolve as _resolve_template
```

and replace both `_load_style_spec(template_path)` calls (~1407, ~1463) with
`_resolve_template(template_path).style`.

In `src/reportbuilder/api/routes_render.py`, replace lines 170-171:

```python
                from reportbuilder.render.template_cache import resolve
                style = resolve(template_path).style
```

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest tests/suite tests/rb -q -m "not judge and not integration" --ignore=tests/suite/integration/api/test_oidc_failure_modes.py`
Expected: PASS. A failure here most likely means a caller mutates the style it
gets back — it is shared now, so that is a real bug to fix rather than a test to
relax.

- [ ] **Step 8: Check the saving actually happened**

Render a deck and confirm the template is parsed once, not per slide:

```bash
uv run python -c "
from unittest.mock import patch
import reportbuilder.render.style_spec as ss
calls = []
orig = ss.load_style_spec
with patch.object(ss, 'load_style_spec', lambda p: (calls.append(p), orig(p))[1]):
    from reportbuilder.render.template_cache import resolve
    for _ in range(60): resolve('<a template path>')
print('load_style_spec calls for 60 slides:', len(calls))
"
```

Expected: `1`.

- [ ] **Step 9: Commit**

```bash
git add src/reportbuilder/render/template_cache.py \
        src/reportbuilder/render/style_spec.py \
        src/reportbuilder/render/image/slide_chrome.py \
        src/reportbuilder/api/routes_questions.py \
        src/reportbuilder/api/routes_render.py \
        tests/suite/unit/render/test_template_cache.py
git commit -m "perf(render): resolve a template once -- style, fonts and sizes together"
```

---

### Task 2: A re-uploaded template of the same length must be picked up

**Files:**
- Modify: `src/reportbuilder/api/routes_questions.py:1327-1333` (`_preview_template`)
- Test: `tests/suite/unit/api/test_preview_template_identity.py`

**Interfaces:**
- Consumes: `template_cache.resolve` from Task 1 — the cache this bug would poison.
- Produces: nothing new; `_preview_template` keeps its `(path, id)` return.

`_preview_template` writes its temp copy only when
`not f.exists() or f.stat().st_size != len(blob)`. Two different templates of
the same byte length therefore share one file — and after Task 1 they would also
share one cached resolution. Key the file on the blob's content hash.

- [ ] **Step 1: Write the failing test**

```python
"""A re-uploaded template is a different template, whatever its length."""
from __future__ import annotations

import hashlib

from reportbuilder.api.routes_questions import _preview_template_filename


def test_same_length_different_bytes_get_different_files():
    a = b"A" * 4096
    b = b"B" * 4096
    assert _preview_template_filename("tpl-1", a) != _preview_template_filename("tpl-1", b)


def test_identical_bytes_get_the_same_file():
    blob = b"A" * 4096
    assert _preview_template_filename("tpl-1", blob) == _preview_template_filename("tpl-1", blob)


def test_the_name_carries_the_content_hash():
    blob = b"A" * 4096
    assert hashlib.sha256(blob).hexdigest()[:16] in _preview_template_filename("tpl-1", blob)
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/suite/unit/api/test_preview_template_identity.py -q`
Expected: FAIL — `ImportError: cannot import name '_preview_template_filename'`.

- [ ] **Step 3: Add the helper and use it**

In `src/reportbuilder/api/routes_questions.py`, above `_preview_template`:

```python
def _preview_template_filename(template_id: str, blob: bytes) -> str:
    """The temp-file name for this exact template CONTENT.

    Named by content hash, not by size. The previous rule rewrote the file only
    when its length differed, so re-uploading a template that happened to be
    the same number of bytes kept serving the old one — and, now that
    resolution is cached on the file, would have kept the old fonts and palette
    too.
    """
    digest = hashlib.sha256(blob).hexdigest()[:16]
    return f"{template_id or 'default'}.{digest}.pptx"
```

Add `import hashlib` to the module's imports if it is not already there.

Then replace the write block inside `_preview_template` (lines ~1327-1333):

```python
        f = path / _preview_template_filename(template_id, blob)
        if not f.exists():
            f.write_bytes(blob)
        return str(f), template_id or "default"
```

- [ ] **Step 4: Run the test — it should pass**

Run: `uv run pytest tests/suite/unit/api/test_preview_template_identity.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/api/routes_questions.py \
        tests/suite/unit/api/test_preview_template_identity.py
git commit -m "fix(preview): name the template temp file by content, not by length"
```

---

### Task 3: Axis names (ticket d95QXiWI)

**Files:**
- Modify: `src/reportbuilder/model/report.py` (ChartSpec)
- Modify: `src/reportbuilder/render/elements.py:96-110`
- Modify: `src/reportbuilder/render/image/_mpl.py`
- Test: `tests/suite/unit/render/test_axis_titles.py`

**Interfaces:**
- Produces: `ChartSpec.axis_x_title: str = ""` and `ChartSpec.axis_y_title: str = ""`.
  Task 8 adds the UI fields that write them; the frontend `ChartSpec` interface
  gains the same two optional fields.

Requirement P-C-27 wants four text properties editable in Design; three exist
and axis names are only a boolean toggle. Empty string means "no axis title",
which is exactly today's appearance, so existing reports are unaffected.

- [ ] **Step 1: Write the failing test**

```python
"""Axis titles: set them, and both renderers draw them."""
from __future__ import annotations

from reportbuilder.model.report import ChartSpec, ElementToggles, NumberFormat, SortSpec


def _spec(**kw) -> ChartSpec:
    return ChartSpec(
        question_ref="q1", chart_type="bar", statistic="pct",
        classifying_var=None, number_format=NumberFormat(), sort=SortSpec(),
        template_slot="s1", elements=ElementToggles(), **kw)


def test_axis_titles_default_to_empty():
    s = _spec()
    assert s.axis_x_title == "" and s.axis_y_title == ""


def test_axis_titles_round_trip():
    s = _spec(axis_x_title="Ikäryhmä", axis_y_title="Osuus vastaajista")
    assert s.axis_x_title == "Ikäryhmä"
    assert s.axis_y_title == "Osuus vastaajista"


def test_image_renderer_draws_the_axis_titles():
    """The compositor path is what the Design preview shows."""
    from reportbuilder.render.image import _mpl
    ax = _mpl_axes()
    _mpl.apply_axis_titles(ax, _spec(axis_x_title="X label", axis_y_title="Y label"),
                           ElementToggles(), ink="#222222")
    assert ax.get_xlabel() == "X label"
    assert ax.get_ylabel() == "Y label"


def test_axis_titles_are_suppressed_when_the_toggle_is_off():
    from reportbuilder.render.image import _mpl
    ax = _mpl_axes()
    _mpl.apply_axis_titles(ax, _spec(axis_x_title="X label", axis_y_title="Y label"),
                           ElementToggles(axis_names=False), ink="#222222")
    assert ax.get_xlabel() == ""


def _mpl_axes():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt.subplots()[1]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/suite/unit/render/test_axis_titles.py -q`
Expected: FAIL — `ChartSpec` has no `axis_x_title`.

- [ ] **Step 3: Add the model fields**

In `src/reportbuilder/model/report.py`, on `ChartSpec`, beside the other text
fields:

```python
    # Axis titles (P-C-27). Empty means no axis title, which is how every chart
    # looked before this existed. `elements.axis_names` still governs axis text
    # as a whole: with it off, these are not drawn even when set.
    axis_x_title: str = ""
    axis_y_title: str = ""
```

- [ ] **Step 4: Draw them on the image path**

In `src/reportbuilder/render/image/_mpl.py`, add:

```python
def apply_axis_titles(ax, chart, elements, ink: str) -> None:
    """Draw the author's axis titles, if this chart has axes and wants them.

    Both renderers must agree — a preview that omits what the deck shows is the
    bug this pipeline exists to prevent — so the native path does the same in
    render/elements.py.
    """
    if not getattr(elements, "axis_names", True):
        return
    x = getattr(chart, "axis_x_title", "") or ""
    y = getattr(chart, "axis_y_title", "") or ""
    if x:
        ax.set_xlabel(x, fontsize=10.5, color=ink)
    if y:
        ax.set_ylabel(y, fontsize=10.5, color=ink)
```

Call it from the bar/line/scatter figure builders, right after the axes are
configured and before the figure is returned. Find them with
`grep -n "def build_\|set_xlabel" src/reportbuilder/render/image/*.py`; the
pie/doughnut/radar builders have no axes and must not call it.

- [ ] **Step 5: Draw them on the native path**

In `src/reportbuilder/render/elements.py`, inside the existing
`if elements.axis_names:` block (line ~98), after the tick-label font work:

```python
            x_title = getattr(spec, "axis_x_title", "") or ""
            y_title = getattr(spec, "axis_y_title", "") or ""
            if x_title:
                chart.category_axis.axis_title.text_frame.text = x_title
            if y_title:
                chart.value_axis.axis_title.text_frame.text = y_title
```

This sits inside the block's existing `try`, whose `except (AttributeError,
ValueError)` already covers chart types with no axes — pie and doughnut raise
`ValueError("chart has no value axis")` there today. Confirm `spec` is the
name that block already has for the ChartSpec; if it is called something else,
use that name.

- [ ] **Step 6: Run the tests — they should pass**

Run: `uv run pytest tests/suite/unit/render/test_axis_titles.py -q`
Expected: PASS (4 tests).

- [ ] **Step 7: Run the whole suite**

Run: `uv run pytest tests/suite tests/rb -q -m "not judge and not integration" --ignore=tests/suite/integration/api/test_oidc_failure_modes.py`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/reportbuilder/model/report.py src/reportbuilder/render/elements.py \
        src/reportbuilder/render/image/_mpl.py tests/suite/unit/render/test_axis_titles.py
git commit -m "feat(charts): editable axis titles, drawn by both renderers (P-C-27)"
```

---

### Task 4: Bottom-2 / bottom-3 (ticket A9JtdqPZ)

**Files:**
- Modify: `src/reportbuilder/model/report.py:10,75,157` (sort basis + row summary)
- Modify: `src/reportbuilder/stats/sorting.py:8`
- Modify: `src/reportbuilder/stats/engine.py:544,758,1502,1580`
- Modify: `src/reportbuilder/plugins/config_schema.py:111,247`
- Modify: `web/src/lib/api.ts:134,219`, `web/src/lib/charts.ts:209,262`
- Test: `tests/suite/unit/stats/test_bottom_box_sort.py` (already written, failing)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: sort bases `"bottom2"`/`"bottom3"` and row-summary functions
  `"bottom2_sum"`/`"bottom3_sum"`, named to match the existing `top2`/`top3`
  and `top2_sum`/`top3_sum`.

The tests already exist and already fail; they are the specification. Read them
first — `tests/suite/unit/stats/test_bottom_box_sort.py` — especially
`test_bottom_is_not_merely_top_reversed`, which is the case a naive
implementation gets wrong.

- [ ] **Step 1: Run the existing tests and read the failures**

Run: `uv run pytest tests/suite/unit/stats/test_bottom_box_sort.py -q`
Expected: FAIL, 5 tests.

- [ ] **Step 2: Find how top2/top3 is implemented**

Run: `grep -rn "top2\|top3\|topbox" src/reportbuilder/stats/ src/reportbuilder/model/report.py src/reportbuilder/plugins/config_schema.py`

Every site that names a top-box variant needs its bottom-box mirror. The
existing implementation is the template to follow; the difference is which end
of the scale is summed — the LOWEST n levels rather than the highest.

- [ ] **Step 3: Add the bottom-box variants**

Mirror each top-box site. In `engine.py:544`, `_top_scale_categories` gains a
`lowest: bool = False` parameter selecting the low end of the ordered scale
instead of the high end; the sort bases and the row-summary function dispatch
follow the same pattern their top-box counterparts already use.

- [ ] **Step 4: Run the tests — they should pass**

Run: `uv run pytest tests/suite/unit/stats/test_bottom_box_sort.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Expose the options in the UI**

Add `"bottom2"`/`"bottom3"` beside `"top2"`/`"top3"` in `web/src/lib/api.ts:134`
(sort basis union) and `219` (row-summary function union), and their labels in
`web/src/lib/charts.ts:209,262` — matching the wording of the top-box entries
already there.

- [ ] **Step 6: Build the frontend**

Run: `cd web && npm run build`
Expected: `✓ built`.

- [ ] **Step 7: Run the whole backend suite**

Run: `uv run pytest tests/suite tests/rb -q -m "not judge and not integration" --ignore=tests/suite/integration/api/test_oidc_failure_modes.py`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add -A src/reportbuilder tests/suite/unit/stats/test_bottom_box_sort.py web/src/lib
git commit -m "feat(stats): bottom-2 and bottom-3 sorting and row summary"
```

---

### Task 5: The fingerprints, with a test runner

**Files:**
- Create: `web/src/lib/previewFingerprint.ts`
- Create: `web/src/lib/previewFingerprint.test.ts`
- Modify: `web/package.json`, `web/vite.config.ts`
- Test: `cd web && npm test`

**Interfaces:**
- Produces:
  - `imageFingerprint(chart: ChartSpec, ctx: RenderContext): string`
  - `interface RenderContext { templateRef: string; reportId: string; groupingKey: string; renderTitle: boolean }`
  - `IMAGE_FINGERPRINT_IGNORED: readonly string[]`
- Consumes: `titleDataKey` from `web/src/lib/charts.ts` (unchanged).

This is the heart of the design, it is pure, and it is where the bug the user
keeps hitting lives — so it gets the project's first frontend unit tests.

- [ ] **Step 1: Add vitest**

```bash
cd web && npm install -D vitest
```

Add to `web/package.json` scripts:

```json
    "test": "vitest run",
```

Add to `web/vite.config.ts`, inside the exported config object:

```ts
  test: { environment: "node", include: ["src/**/*.test.ts"] },
```

and change the file's first import line to
`import { defineConfig } from "vitest/config";` so the `test` key type-checks.

- [ ] **Step 2: Write the failing test**

```ts
import { describe, expect, it } from "vitest";
import { imageFingerprint, IMAGE_FINGERPRINT_IGNORED } from "./previewFingerprint";
import { titleDataKey } from "./charts";
import type { ChartSpec } from "./api";

const CTX = { templateRef: "", reportId: "r1", groupingKey: "{}", renderTitle: false };

function chart(over: Partial<ChartSpec> = {}): ChartSpec {
  return {
    question_ref: "q1", chart_type: "bar", statistic: "pct", classifying_var: null,
    number_format: {}, sort: {}, template_slot: "s1", elements: {},
    scatter_xy: null, show_not_answered: false, show_empty_categories: true,
    not_answered_codes: null, category_label_overrides: [],
    slide_title: "A title", slide_description: null, footer_note: null,
    ...over,
  } as unknown as ChartSpec;
}

describe("imageFingerprint", () => {
  it("changes when the chart type changes", () => {
    expect(imageFingerprint(chart(), CTX))
      .not.toBe(imageFingerprint(chart({ chart_type: "pie" }), CTX));
  });

  it("changes when a NEW field changes — the deny-list property", () => {
    // The point of hashing by exclusion: a field nobody remembered to register
    // still invalidates the image. axis_x_title is exactly such a field.
    const withAxis = { ...chart(), axis_x_title: "Ikäryhmä" } as ChartSpec;
    expect(imageFingerprint(chart(), CTX)).not.toBe(imageFingerprint(withAxis, CTX));
  });

  it("changes when the title changes, because the title is baked in", () => {
    expect(imageFingerprint(chart(), CTX))
      .not.toBe(imageFingerprint(chart({ slide_title: "Another" }), CTX));
  });

  it("ignores a reorder", () => {
    // normalizeSlots rewrites template_slot for EVERY chart on any reorder;
    // hashing it would re-render all 60 slides when the user drags one.
    expect(imageFingerprint(chart(), CTX))
      .toBe(imageFingerprint(chart({ template_slot: "s9" }), CTX));
  });

  it("ignores identity and bookkeeping fields", () => {
    const other = chart({ slide_id: "x", compare_group: "g", excluded: true,
                          slide_title_key: "k" } as Partial<ChartSpec>);
    expect(imageFingerprint(chart(), CTX)).toBe(imageFingerprint(other, CTX));
  });

  it("changes with the render context", () => {
    expect(imageFingerprint(chart(), CTX))
      .not.toBe(imageFingerprint(chart(), { ...CTX, templateRef: "tpl-2" }));
  });

  it("lists exactly the five ignored fields", () => {
    expect([...IMAGE_FINGERPRINT_IGNORED].sort()).toEqual(
      ["compare_group", "excluded", "slide_id", "slide_title_key", "template_slot"]);
  });
});

describe("titleDataKey stays presentation-blind", () => {
  const q = { text: "Q", variables: ["v1"] };
  it("is unmoved by chart type, sort, axis titles and row summary", () => {
    const base = titleDataKey(chart(), q);
    expect(titleDataKey(chart({ chart_type: "pie" }), q)).toBe(base);
    expect(titleDataKey(chart({ sort: { basis: "bottom2" } } as Partial<ChartSpec>), q)).toBe(base);
    expect(titleDataKey({ ...chart(), axis_x_title: "X" } as ChartSpec, q)).toBe(base);
    expect(titleDataKey(chart({ row_summary_fn: "bottom2_sum" } as Partial<ChartSpec>), q)).toBe(base);
  });

  it("DOES move when the data changes", () => {
    expect(titleDataKey(chart({ classifying_var: "sukupuoli" }), q))
      .not.toBe(titleDataKey(chart(), q));
  });
});
```

- [ ] **Step 3: Run it and watch it fail**

Run: `cd web && npm test`
Expected: FAIL — cannot resolve `./previewFingerprint`.

- [ ] **Step 4: Write the module**

```ts
import type { ChartSpec } from "./api";

/** What the image does NOT depend on.
 *
 * The list is short and it is the only place this judgement is recorded:
 *  - slide_id / compare_group  — identity and provenance, never drawn
 *  - slide_title_key           — the title producer's own bookkeeping
 *  - template_slot / excluded  — where the slide sits in the deck, not what it shows
 *
 * template_slot earns its place: normalizeSlots rewrites it to `s${i + 1}` for
 * EVERY chart on any reorder (charts.ts), so hashing it would re-render all
 * sixty slides when the author drags one.
 */
export const IMAGE_FINGERPRINT_IGNORED = [
  "slide_id",
  "compare_group",
  "slide_title_key",
  "template_slot",
  "excluded",
] as const;

export interface RenderContext {
  templateRef: string;
  reportId: string;
  groupingKey: string;
  renderTitle: boolean;
}

/** What this slide's image depends on — everything, minus what provably cannot
 *  change a pixel.
 *
 * By EXCLUSION, deliberately. The previous key was an allow-list of 25 fields,
 * which meant every new ChartSpec field had to be remembered there or the
 * preview silently kept showing the old image — a bug that looks like a broken
 * renderer and is invisible in review. Hashing by exclusion inverts the failure:
 * forget to exclude something and you pay one extra render.
 *
 * The title is IN, on purpose: it is baked into the PNG on both render paths,
 * so a title landing makes its own image stale and the slide re-renders exactly
 * once, with no ordering rule to maintain.
 */
export function imageFingerprint(chart: ChartSpec, ctx: RenderContext): string {
  const ignored = new Set<string>(IMAGE_FINGERPRINT_IGNORED);
  const rest: Record<string, unknown> = {};
  for (const k of Object.keys(chart).sort()) {
    if (!ignored.has(k)) rest[k] = (chart as Record<string, unknown>)[k];
  }
  return JSON.stringify([rest, ctx.templateRef, ctx.reportId, ctx.groupingKey, ctx.renderTitle]);
}
```

Key order matters because the output is a string: `Object.keys(...).sort()`
makes it independent of the order fields happen to have been assigned, so a
chart rebuilt by a spread does not look changed.

- [ ] **Step 5: Run the tests — they should pass**

Run: `cd web && npm test`
Expected: PASS (9 tests). If the `titleDataKey` block fails, that is a real
finding, not a test to adjust: it means presentation has leaked into the title
key and titles are being regenerated for cosmetic edits.

- [ ] **Step 6: Commit**

```bash
git add web/package.json web/package-lock.json web/vite.config.ts \
        web/src/lib/previewFingerprint.ts web/src/lib/previewFingerprint.test.ts
git commit -m "feat(preview): fingerprint the image by exclusion, and test it"
```

---

### Task 6: The producer registry and the queue

**Files:**
- Create: `web/src/lib/previewQueue.ts`
- Create: `web/src/lib/previewQueue.test.ts`
- Test: `cd web && npm test`

**Interfaces:**
- Consumes: `imageFingerprint`/`RenderContext` (Task 5), `titleDataKey` (`charts.ts`).
- Produces:
  - `setSlideSource(fn: (slideId: string) => ChartSpec | null)`
  - `setPatchSink(fn: (slideId: string, patch: Partial<ChartSpec>) => void)`
  - `setRenderContext(ctx: RenderContext)`
  - `enqueue(slideId: string)`, `promote(slideId: string)`, `reset(reportId: string)`
  - `isBusy(): boolean`, `subscribe(fn: () => void): () => void`
  - `statusOf(slideId: string): Record<ProducerId, Status>`
  - `type ProducerId = "title" | "bullets" | "chart"`
  - `type Status = "pending" | "running" | "done" | "failed"`

- [ ] **Step 1: Write the failing test**

```ts
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as q from "./previewQueue";
import type { ChartSpec } from "./api";

const slides = new Map<string, ChartSpec>();
function put(id: string, over: Partial<ChartSpec> = {}) {
  slides.set(id, {
    question_ref: "q1", chart_type: "bar", statistic: "pct", classifying_var: null,
    number_format: {}, sort: {}, template_slot: "s1", elements: {}, scatter_xy: null,
    show_not_answered: false, show_empty_categories: true, not_answered_codes: null,
    category_label_overrides: [], slide_title: null, slide_description: null,
    footer_note: null, slide_id: id, ...over,
  } as unknown as ChartSpec);
}

beforeEach(() => {
  slides.clear();
  q.reset("r1");
  q.setSlideSource((id) => slides.get(id) ?? null);
  q.setPatchSink((id, patch) => put(id, { ...slides.get(id), ...patch } as Partial<ChartSpec>));
  q.setRenderContext({ templateRef: "", reportId: "r1", groupingKey: "{}", renderTitle: false });
});

describe("the queue", () => {
  it("runs the title before the image, so a slide renders once", async () => {
    const order: string[] = [];
    put("s1");
    q.__setProducersForTest([
      { id: "title", fingerprint: () => "t", storedFingerprint: () => null,
        run: async () => { order.push("title"); return { slide_title: "Made" }; },
        onFailure: "continue" },
      { id: "chart", fingerprint: () => "c", storedFingerprint: () => null,
        run: async (ctx) => { order.push(`chart:${ctx.chart.slide_title}`); },
        onFailure: "abort" },
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    // The image producer must see the title the title producer just wrote —
    // patches flush to React in batches, so it reads the queue's own overlay.
    expect(order).toEqual(["title", "chart:Made"]);
  });

  it("does not re-run a producer whose fingerprint is unchanged", async () => {
    put("s1");
    const run = vi.fn(async () => {});
    q.__setProducersForTest([
      { id: "chart", fingerprint: () => "same", storedFingerprint: () => "same",
        run, onFailure: "abort" },
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(run).not.toHaveBeenCalled();
  });

  it("keeps rendering when a title fails", async () => {
    put("s1");
    const chartRun = vi.fn(async () => {});
    q.__setProducersForTest([
      { id: "title", fingerprint: () => "t", storedFingerprint: () => null,
        run: async () => { throw new Error("egoHive down"); }, onFailure: "continue" },
      { id: "chart", fingerprint: () => "c", storedFingerprint: () => null,
        run: chartRun, onFailure: "abort" },
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(chartRun).toHaveBeenCalled();
    expect(q.statusOf("s1").title).toBe("failed");
  });

  it("stops the item when an aborting producer fails", async () => {
    put("s1");
    const after = vi.fn(async () => {});
    q.__setProducersForTest([
      { id: "chart", fingerprint: () => "c", storedFingerprint: () => null,
        run: async () => { throw new Error("render failed"); }, onFailure: "abort" },
      { id: "bullets", fingerprint: () => "b", storedFingerprint: () => null,
        run: after, onFailure: "continue" },
    ]);
    q.enqueue("s1");
    await q.__drainForTest();
    expect(after).not.toHaveBeenCalled();
  });

  it("promotes a slide to the head of the queue", async () => {
    const done: string[] = [];
    ["a", "b", "c"].forEach((id) => put(id));
    q.__setProducersForTest([
      { id: "chart", fingerprint: () => "c", storedFingerprint: () => null,
        run: async (ctx) => { done.push(ctx.slideId); }, onFailure: "abort" },
    ]);
    q.__setConcurrencyForTest(1);
    ["a", "b", "c"].forEach(q.enqueue);
    q.promote("c");
    await q.__drainForTest();
    expect(done[0]).toBe("c");
  });

  it("drops a slide that was deleted while queued", async () => {
    put("gone");
    const run = vi.fn(async () => {});
    q.__setProducersForTest([
      { id: "chart", fingerprint: () => "c", storedFingerprint: () => null,
        run, onFailure: "abort" },
    ]);
    q.enqueue("gone");
    slides.delete("gone");
    await q.__drainForTest();
    expect(run).not.toHaveBeenCalled();
  });

  it("is busy while work is outstanding and idle after", async () => {
    put("s1");
    q.__setProducersForTest([
      { id: "chart", fingerprint: () => "c", storedFingerprint: () => null,
        run: async () => {}, onFailure: "abort" },
    ]);
    q.enqueue("s1");
    expect(q.isBusy()).toBe(true);
    await q.__drainForTest();
    expect(q.isBusy()).toBe(false);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npm test`
Expected: FAIL — cannot resolve `./previewQueue`.

- [ ] **Step 3: Write the module**

Write `web/src/lib/previewQueue.ts` implementing the interface above. The
structure, which the tests pin down:

```ts
export type ProducerId = "title" | "bullets" | "chart";
export type Status = "pending" | "running" | "done" | "failed";

export interface ProducerCtx {
  slideId: string;
  chart: ChartSpec;          // draft merged with this queue's unflushed patches
  ctx: RenderContext;
}

export interface Producer {
  id: ProducerId;
  fingerprint(c: ProducerCtx): string;
  storedFingerprint(c: ProducerCtx): string | null;
  run(c: ProducerCtx): Promise<Partial<ChartSpec> | void>;
  onFailure: "continue" | "abort";
}
```

The single sequential function, which is the whole point of the design:

```ts
async function producePreview(slideId: string): Promise<void> {
  for (const p of PRODUCERS) {
    const c = readSlide(slideId);        // re-read: draft + overlay, every time
    if (!c) return;                      // slide deleted while queued
    if (!needed(p, c)) continue;
    const fp = p.fingerprint(c);         // capture what we are about to satisfy
    setStatus(slideId, p.id, "running");
    try {
      applyPatch(slideId, (await p.run(c)) || {});
      setStatus(slideId, p.id, "done", fp);
    } catch (e) {
      setStatus(slideId, p.id, "failed", fp, e);
      if (p.onFailure === "abort") return;
    }
  }
  const c = readSlide(slideId);
  if (c && PRODUCERS.some((p) => needed(p, c))) enqueue(slideId);
}
```

Three things carry the correctness, and all three are pinned by a test above:

- `needed(p, c)` is `p.storedFingerprint(c) === null || p.storedFingerprint(c) !== p.fingerprint(c)`.
- `applyPatch` writes to the **overlay synchronously** and schedules a flush to
  `patchSink` in a microtask. `readSlide` returns `slideSource(id)` merged with
  the overlay, and the flush drops what it wrote — so producers read their own
  writes, and the overlay can never shadow a later user edit.
- `markDone` stores the fingerprint captured **before** `run`, never one
  re-read after it, which would record work that was never done.

The real `PRODUCERS` array is `[title, bullets, chart]`:

- `title` — `fingerprint` = `titleDataKey(chart, resolvedQuestion)`,
  `storedFingerprint` = `chart.slide_title_key ?? null`, `run` calls
  `api.materials.aiSlideTitle` and returns `{ slide_title, slide_title_key }`,
  `onFailure: "continue"`.
- `bullets` — themes slides only; `fingerprint` = `chart.question_ref`,
  `storedFingerprint` = `question_ref` when `options.bullets` is non-empty else
  `null` (deliberately generate-once), `run` calls `api.materials.aiThemes`,
  `onFailure: "continue"`.
- `chart` — `fingerprint` = `imageFingerprint(chart, ctx)`,
  `storedFingerprint` = the queue's completed-fingerprint entry, `run` calls
  `api.materials.previewChart` and writes the blob into the React Query cache
  under the same fingerprint, `onFailure: "abort"`.

Concurrency is per producer kind, not one global number; the old global 3 was
sized for LibreOffice and the Design step now uses the compositor. Expose
`__setConcurrencyForTest`, `__setProducersForTest` and `__drainForTest` (a
promise that resolves when the queue goes idle) for the tests above.

- [ ] **Step 4: Run the tests — they should pass**

Run: `cd web && npm test`
Expected: PASS (16 tests, Task 5's included).

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/previewQueue.ts web/src/lib/previewQueue.test.ts
git commit -m "feat(preview): one queue, one sequential producer function"
```

---

### Task 7: Move the wizard onto the queue, and delete the old machinery

**Files:**
- Modify: `web/src/components/wizard/ReportWizard.tsx`
- Modify: `web/src/components/wizard/StepConfigure.tsx:1515-1545,1740,1758,1830-1833`
- Modify: `web/src/components/wizard/ChartThumb.tsx`
- Modify: `web/src/lib/api.ts:405-470`, `web/src/lib/queries.ts:364,446-510`
- Delete: `web/src/components/wizard/SlideTitleOverlay.tsx`

**Interfaces:**
- Consumes: everything Task 6 produces.
- Produces: nothing new. This task removes code.

This is the one change that cannot be half-done: it deletes the two queues it
replaces. Do it in one commit and verify with Task 9 before moving on.

- [ ] **Step 1: Wire the wizard to the queue**

In `ReportWizard.tsx`, on mount, register the seams and reset per report:

```tsx
  useEffect(() => {
    previewQueue.reset(reportId);
    previewQueue.setSlideSource((id) =>
      draftRef.current?.charts.find((c) => c.slide_id === id) ?? null);
    previewQueue.setPatchSink((id, patch) => updateChartById(id, patch));
  }, [reportId, updateChartById]);
```

Enqueue the deck whenever the chart list changes — `enqueue` dedupes and
`needed()` filters, so re-enqueueing a settled deck costs nothing:

```tsx
  useEffect(() => {
    for (const c of draft?.charts ?? []) if (c.slide_id) previewQueue.enqueue(c.slide_id);
  }, [draft?.charts]);
```

- [ ] **Step 2: Make saving follow the queue**

Replace the `aiBusy` term in the autosave effect with the queue's own idea of
busy, subscribed so the effect re-runs when it changes:

```tsx
  const busy = useSyncExternalStore(previewQueue.subscribe, previewQueue.isBusy);
```

and use `busy` where `aiBusy` was. Keep the `MAX_AI_SAVE_HOLD_MS` cap exactly as
it is: it is what guarantees a stranded producer can never mean the author's
typing is lost.

- [ ] **Step 3: Delete the old title queue**

From `ReportWizard.tsx` remove `TITLE_CONCURRENCY`, `titlesAttempted`,
`titleQueue`, `titleActive`, `runTitle`, `pumpTitles`, `ensureTitles`,
`clearAiPending`, the `aiPending` state and the `aiBusy` memo — and the props
that carried them into `StepConfigure`.

- [ ] **Step 4: Delete the old render gate**

From `web/src/lib/api.ts` remove `PREVIEW_CONCURRENCY`, `PRIORITY_RESERVE`,
`previewActive`, `activePreviewKey`, `previewQueue`, `setActivePreviewKey`,
`pumpPreview` and `serializePreview`, and the `serializePreview(...)` wrapper
around the `previewChart` fetch — the queue provides that limit now.

From `web/src/lib/queries.ts` remove `previewContentKey` and the
`setActivePreviewKey` effect in `useChartPreview`, keying the query on
`imageFingerprint(chart, ctx)` instead.

- [ ] **Step 5: Simplify the consumers**

In `StepConfigure.tsx`: drop the `aiPending` prop and its type from
`DeckPrefetch` and the panel, drop the `charts.filter(...titlePending)` line
(the queue owns ordering now), and read pending state from
`previewQueue.statusOf(slideId)` where the placeholders need it. In
`ChartThumb.tsx`, drop the `titlePending` prop. Call `previewQueue.promote(slideId)`
when a slide becomes the active one.

- [ ] **Step 6: Delete the dead overlay**

```bash
git rm web/src/components/wizard/SlideTitleOverlay.tsx
```

Nothing imports it — confirm with `grep -rn "SlideTitleOverlay" web/src`.

- [ ] **Step 7: Build and unit-test**

Run: `cd web && npm run build && npm test`
Expected: `✓ built`, and the vitest suites still pass.

- [ ] **Step 8: Commit**

```bash
git add -A web/src
git commit -m "refactor(preview): one queue owns generation and rendering"
```

---

### Task 8: The axis-name fields in Design

**Files:**
- Modify: `web/src/lib/api.ts` (ChartSpec interface)
- Modify: `web/src/components/wizard/StepConfigure.tsx:927-940` (beside Slide title/Subtitle)

**Interfaces:**
- Consumes: `ChartSpec.axis_x_title` / `axis_y_title` from Task 3.

- [ ] **Step 1: Add the fields to the client type**

In `web/src/lib/api.ts`, on `ChartSpec`, after `slide_description`:

```ts
  // Axis titles (P-C-27). Empty = no axis title. Presentation only: they are in
  // the image fingerprint and deliberately NOT in titleDataKey, so editing one
  // re-renders the slide without spending an LLM call on a new headline.
  axis_x_title?: string;
  axis_y_title?: string;
```

- [ ] **Step 2: Add the two text fields**

In `StepConfigure.tsx`, beside the existing "Slide title" and "Subtitle" fields
(around line 927), following the same `<Field label=…><Textarea…/></Field>`
shape those use — single-line `<Input>` rather than `<Textarea>`, since an axis
title is a few words:

```tsx
      <Field label="X axis title">
        <Input
          value={chart.axis_x_title ?? ""}
          onChange={(e) => onChange({ axis_x_title: e.target.value })}
        />
      </Field>
      <Field label="Y axis title">
        <Input
          value={chart.axis_y_title ?? ""}
          onChange={(e) => onChange({ axis_y_title: e.target.value })}
        />
      </Field>
```

Match the import and prop names the surrounding fields use; if the file's input
component is not called `Input`, use whatever the neighbouring single-line
fields use.

- [ ] **Step 3: Build**

Run: `cd web && npm run build`
Expected: `✓ built`.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/api.ts web/src/components/wizard/StepConfigure.tsx
git commit -m "feat(design): axis title fields (P-C-27)"
```

---

### Task 9: End-to-end acceptance

**Files:**
- Create: `scripts/e2e/preview_pipeline.mjs`
- Create: `scripts/e2e/mint_session.py`

**Interfaces:**
- Consumes: the whole stack.

The frontend has no component tests, so the acceptance criteria are measured
against the running app. The driver counts network calls, which is exactly what
the spec's table is written in terms of.

- [ ] **Step 1: Bring the stack up**

```bash
./scripts/dev-stack.sh up
```

- [ ] **Step 2: Mint a session**

`scripts/e2e/mint_session.py` resolves a user through the backend's own auth
module and prints a signed cookie:

```python
"""Print a session cookie for a local user, so a browser driver can sign in."""
import sys

from reportbuilder.api.deps_store import build_repository, service_auth
from reportbuilder.auth import session as S
from reportbuilder.auth.keys import get_or_create_signing_key

auth = service_auth()
repo = build_repository()
target = next((u for u in repo.list_users(auth)
               if u.email.lower() == sys.argv[1].lower()), None)
if target is None:
    sys.exit(f"no user {sys.argv[1]}")
print(S.cookie_value(get_or_create_signing_key(repo, auth), S.create(repo, auth, target.id)))
```

Run it with the same datahive settings the dev backend uses:

```bash
TOKEN=$(python3 -c "import json;d=json.load(open('work/datahive_creds.json'));print(d.get('bearer_admin') or d['bearer'])")
NSIGHT_DATAHIVE_URL=http://127.0.0.1:7910 NSIGHT_DATAHIVE_TOKEN="$TOKEN" PYTHONPATH=src \
  .venv/bin/python scripts/e2e/mint_session.py <your-email> > work/e2e-cookie.txt
```

- [ ] **Step 3: Write the driver**

`scripts/e2e/preview_pipeline.mjs` signs in with that cookie, opens a
60-slide report at the Design step, and counts requests by kind
(`ai/slide-title`, `preview-chart`, `PUT …/reports/…`). Import Playwright from
the web workspace: `import { chromium } from "../../web/node_modules/playwright-core/index.mjs"`,
and launch with `{ channel: "chrome", headless: true }`.

Prepare a title-less report to measure a cold generation phase by copying an
existing one and stripping `slide_title`/`slide_title_key` from every chart,
then POSTing it to `/cases/{caseId}/reports`.

- [ ] **Step 4: Run the acceptance table**

| Scenario | Expected |
|---|---|
| Open Design on a title-less report | 60 title calls, 60 renders, **1** save |
| Open Design on a fully titled report | 0 title calls, 0 renders, 0 saves |
| Change one chart's type | 1 render, **0** title calls |
| Edit an axis name | 1 render, **0** title calls |
| Edit a slide title by hand | 1 render, 1 save, no title call |
| Click an unrendered slide mid-warm-up | it renders next |
| LLM title fails | slide still renders; failure shown in the warning button |
| Design → Preview | no re-render; the same images |

Measured baseline before this work: 60 titles → 17 saves after the interim fix,
28 in the original log.

Simulate the failure row by pointing the AI base URL at a closed port for one
run, or by temporarily returning a rejected promise from the `title` producer's
`run` — the assertion is that the image still appears.

- [ ] **Step 5: Look at a rendered slide**

Screenshot the Design step and open the image. A green test run says the counts
are right; only looking says the slide is. Check the title is the template's
face at the template's size, the subtitle sits above the chart, and an axis
title appears where one was set.

- [ ] **Step 6: Commit**

```bash
git add scripts/e2e
git commit -m "test(preview): end-to-end acceptance for the preview pipeline"
```

---

## Self-review

**Spec coverage.** §1 template cache → Task 1, which removes both per-slide
costs (the `.pptx` parse and the per-slide `build_spec`) rather than caching
around them. §1's inherited temp-file bug
→ Task 2. §2 fingerprints → Task 5. §3 registry and §4 sequential function →
Task 6. §5 failure → Task 6 (two tests). §6 queue → Task 6. §7 wizard and saving
→ Task 7. §8 deletions → Task 7. Scope: axis names → Tasks 3 and 8; bottom-2/3 →
Task 4. Verification → Tasks 1-6 unit tests and Task 9 end-to-end.

**Naming.** `resolve()`/`ResolvedTemplate` (Task 1) are used verbatim in Tasks 1
and 2. `imageFingerprint`/`RenderContext`/`IMAGE_FINGERPRINT_IGNORED` (Task 5)
are consumed unchanged in Tasks 6 and 7. `ProducerId`/`Status`/`ProducerCtx`
(Task 6) are consumed unchanged in Task 7. `axis_x_title`/`axis_y_title` are
spelled identically in Tasks 3, 5 and 8.

**Ordering.** Tasks 1-4 are backend and independently shippable. Task 5 must
precede 6 (fingerprints), 6 must precede 7 (the queue it wires in), 3 must
precede 8 (the model fields the UI writes). Task 9 verifies everything and runs
last.
