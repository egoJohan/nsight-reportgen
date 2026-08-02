# Compare Groups Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** From the Add-slide button, generate a section of slides comparing a study's groups (e.g. Pakkausilme 1 vs 2) across chosen questions, leaving the total-level slides in place.

**Architecture:** No engine or renderer change — `classifying_var` already produces the two-series chart. The work is two `ChartSpec` fields (`slide_id`, `compare_group`), one read-only endpoint that reports which questions a classifier actually splits, and a frontend dialog that generates the slides.

**Tech Stack:** Python 3.13, FastAPI, pytest; React + TypeScript (Vite).

**Spec:** `docs/superpowers/specs/2026-08-02-compare-groups-section-design.md`

## Global Constraints

- Backend tests: `.venv/bin/python -m pytest tests/suite -q` from `/home/johan/Projects/nsight/proto`. `tests/rb` must also stay green.
- Frontend typecheck: `cd web && npx tsc --noEmit -p tsconfig.app.json`.
- The backend CANONICALISES reports (`report_from_json` → `report_to_json` in `routes_reports._canonicalize`), so any field not on `ChartSpec` is dropped on save. Both new fields must be real `ChartSpec` fields.
- Neither new field may enter the preview cache key (`web/src/lib/queries.ts`) — they change no pixel.
- Client fixture: case `case-erisan` / `mat-erisan`, report `rep-erisan`. Under `Polku`, 12 of its 18 questions split and 6 do not.
- Never commit `*.sav` or anything under `work/`.
- Commit after each task.

---

### Task 1: `slide_id` and `compare_group` on ChartSpec (spec §3)

**Files:**
- Modify: `src/reportbuilder/model/report.py`
- Test: `tests/suite/unit/model/test_slide_identity.py` (create)

**Interfaces:**
- Produces: `ChartSpec.slide_id: str = ""` and `ChartSpec.compare_group: str | None = None`; `report_from_json` assigns a deterministic `slide_id` when absent; `report_to_json` emits both.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/unit/model/test_slide_identity.py`:

```python
"""Per-chart identity. Charts were identified by question_ref, so one question
could not own two slides — which a comparison section requires.
(spec 2026-08-02-compare-groups-section §3)"""
from __future__ import annotations

from reportbuilder.model.report import report_from_json, report_to_json


def _report(charts):
    return {"template_ref": "t", "render_mode": "image", "charts": charts}


def _chart(**kw):
    base = {"question_ref": "q1", "chart_type": "horizontal_bar", "statistic": "pct",
            "classifying_var": None, "template_slot": "s"}
    base.update(kw)
    return base


def test_missing_slide_id_is_assigned_deterministically():
    """Old reports have none; loading must not renumber them on every save."""
    doc = _report([_chart(question_ref="a"), _chart(question_ref="b")])
    first = [c.slide_id for c in report_from_json(doc).charts]
    second = [c.slide_id for c in report_from_json(doc).charts]
    assert first == second
    assert all(sid for sid in first)


def test_two_charts_for_one_question_get_distinct_ids():
    doc = _report([_chart(question_ref="a"), _chart(question_ref="a")])
    ids = [c.slide_id for c in report_from_json(doc).charts]
    assert len(set(ids)) == 2


def test_an_explicit_slide_id_is_preserved():
    doc = _report([_chart(question_ref="a", slide_id="keep-me")])
    assert report_from_json(doc).charts[0].slide_id == "keep-me"


def test_compare_group_round_trips():
    doc = _report([_chart(question_ref="a", compare_group="polku")])
    r = report_from_json(doc)
    assert r.charts[0].compare_group == "polku"
    again = report_from_json(json_loads(report_to_json(r)))
    assert again.charts[0].compare_group == "polku"


def test_compare_group_defaults_to_none():
    assert report_from_json(_report([_chart()])).charts[0].compare_group is None


def test_both_fields_survive_a_canonicalising_round_trip():
    """routes_reports canonicalises on save: from_json -> to_json. A field the
    model does not know is silently dropped, so these must be real fields."""
    doc = _report([_chart(question_ref="a", slide_id="s1", compare_group="polku")])
    out = json_loads(report_to_json(report_from_json(doc)))
    assert out["charts"][0]["slide_id"] == "s1"
    assert out["charts"][0]["compare_group"] == "polku"


def json_loads(s):
    import json
    return json.loads(s)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/unit/model/test_slide_identity.py -q`
Expected: FAIL — `ChartSpec` has no `slide_id`.

- [ ] **Step 3: Add the fields**

In `src/reportbuilder/model/report.py`, on `ChartSpec` (after `footer_note`):

```python
    # Per-chart identity. question_ref says WHICH QUESTION a chart shows and is no
    # longer unique: a comparison section adds a second slide for a question that
    # already has a total-level one. Empty on reports saved before this existed;
    # report_from_json fills it in deterministically. (spec 2026-08-02 compare-groups §3)
    slide_id: str = ""
    # Set on a slide generated by the "Compare groups" section, to the variable it
    # was grouped by. Marks the slide as NOT the question's primary slide, so the
    # Step 1 question toggle leaves it alone.
    compare_group: str | None = None
```

In `report_from_json`'s chart builder, pass them through, and assign a fallback id:

```python
            slide_id=str(c.get("slide_id") or "") or f"{c.get('question_ref', '')}#{idx}",
            compare_group=(c.get("compare_group") or None),
```

The builder needs the chart's index — enumerate the chart list where `_chart(c)` is called. In `report_to_json`, emit `slide_id` and `compare_group` alongside the other chart fields.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass. A serde test asserting an exact chart-dict key set will need the two new keys added.

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/model/report.py tests/suite/unit/model/test_slide_identity.py
git commit -m "feat(model): per-chart slide_id and compare_group"
```

---

### Task 2: `GET /materials/{id}/split-groups` (spec §1.1)

**Files:**
- Modify: `src/reportbuilder/api/routes_questions.py`
- Test: `tests/suite/integration/api/test_split_groups.py` (create)

**Interfaces:**
- Consumes: `_classifier_masks`, `_drop_empty_segments` from `stats.engine`.
- Produces: `GET /materials/{id}/split-groups?classifying_var=<name-or-qid>&grouping=<json>` → `{"groups": {"<qid>": <int>, …}}` — how many groups would actually appear for each question in the material.

- [ ] **Step 1: Write the failing test**

Create `tests/suite/integration/api/test_split_groups.py`:

```python
"""Which questions does a classifier actually split? The dialog must not offer a
question whose split yields one group — 6 of the customer's 18 do.
(spec 2026-08-02-compare-groups-section §1.1)"""
from __future__ import annotations

import json
import pathlib

import pytest

_STORE = pathlib.Path("work/demo-store")


@pytest.fixture
def client():
    import os

    os.environ["NSIGHT_DEMO"] = "1"
    os.environ["NSIGHT_DEMO_DIR"] = str(_STORE)
    from fastapi.testclient import TestClient

    from reportbuilder.api.server import build_server_app

    return TestClient(build_server_app())


def _skip_without_fixture():
    if not (_STORE / "materials" / "mat-erisan.sav").exists():
        pytest.skip("mat-erisan not available locally")


def test_reports_two_groups_for_a_question_everyone_answered(client):
    _skip_without_fixture()
    r = client.get("/materials/mat-erisan/split-groups",
                   params={"classifying_var": "polku"})
    assert r.status_code == 200
    groups = r.json()["groups"]
    assert groups["var3"] == 2


def test_reports_one_group_for_a_single_arm_battery(client):
    """A battery asked only of path 1 yields that arm and nothing else."""
    _skip_without_fixture()
    rep = json.loads(json.loads((_STORE / "reports.json").read_text())["rep-erisan"])
    r = client.get("/materials/mat-erisan/split-groups",
                   params={"classifying_var": "polku",
                           "grouping": json.dumps(rep["grouping"])})
    groups = r.json()["groups"]
    single_arm = [q for q, n in groups.items()
                  if q.startswith("battery-") and n < 2]
    assert single_arm, "expected the single-arm batteries to report one group"


def test_unknown_classifier_reports_no_groups(client):
    _skip_without_fixture()
    r = client.get("/materials/mat-erisan/split-groups",
                   params={"classifying_var": "does-not-exist"})
    assert r.status_code == 200
    assert all(n < 2 for n in r.json()["groups"].values())


def test_missing_classifier_is_a_422(client):
    _skip_without_fixture()
    assert client.get("/materials/mat-erisan/split-groups").status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_split_groups.py -q`
Expected: FAIL with 404 — the route does not exist.

- [ ] **Step 3: Add the endpoint**

In `src/reportbuilder/api/routes_questions.py`:

```python
@questions_router.get("/materials/{material_id}/split-groups")
def split_groups(
    material_id: str,
    classifying_var: str,
    grouping: str | None = None,
    client: DataHiveClient = Depends(get_client),
) -> dict:
    """How many groups each question would actually show if split by
    `classifying_var` — the "Compare groups" dialog disables the ones below 2.

    Counts with the ENGINE's own helpers so the dialog can never disagree with the
    chart: a battery whose members belong to a single study arm yields one group,
    not two. (spec 2026-08-02 compare-groups §1.1)"""
    from reportbuilder.stats.engine import _classifier_masks, _drop_empty_segments

    df, model = _load_df_model(material_id, client)
    if grouping:
        try:
            model = apply_grouping_override(model, json.loads(grouping), df=df)
        except (ValueError, TypeError):
            pass

    class _Spec:                     # the two attributes _classifier_masks reads
        classifying_var = None
        classifying_var_2 = None

    spec = _Spec()
    spec.classifying_var = classifying_var
    masks = _classifier_masks(spec, df, model)
    out: dict[str, int] = {}
    for q in model.questions:
        if not masks:
            out[q.qid] = 0
            continue
        vars_ = [model.variables[v] for v in q.variables if v in model.variables]
        kept = _drop_empty_segments(masks, vars_, df) if vars_ else masks
        out[q.qid] = len(kept or {})
    return {"groups": out}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/suite/integration/api/test_split_groups.py -q && .venv/bin/python -m pytest tests/suite tests/rb -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add src/reportbuilder/api/routes_questions.py tests/suite/integration/api/test_split_groups.py
git commit -m "feat(api): report how many groups a classifier splits each question into"
```

---

### Task 3: Frontend types and the generation function (spec §1, §2)

**Files:**
- Modify: `web/src/lib/api.ts` (types + the new call)
- Modify: `web/src/lib/charts.ts` (generation)
- Test: manual — verified end to end in Task 5.

**Interfaces:**
- Consumes: Task 2's endpoint.
- Produces:
  - `api.materials.splitGroups(materialId, classifyingVar, grouping) => Promise<Record<string, number>>`
  - `makeComparisonSlide(source: ChartSpec, classifyingVar: string): ChartSpec` in `charts.ts`
  - `COMPARISON_FALLBACK_TYPE = "horizontal_bar"` and `supportsMultiSeries(chartType): boolean`

- [ ] **Step 1: Add the types**

In `web/src/lib/api.ts`, on `ChartSpec`:

```ts
  // Per-chart identity — question_ref is no longer unique (a comparison section
  // adds a second slide for a question that already has a total-level one).
  slide_id?: string;
  // Set on a slide generated by "Compare groups", to the variable it groups by.
  compare_group?: string | null;
```

and in the `materials` API object:

```ts
    // How many groups each question would ACTUALLY show if split by this variable.
    // A battery whose members belong to one study arm reports 1, so the dialog can
    // disable it instead of generating an unsplit slide.
    splitGroups: (
      materialId: string,
      classifyingVar: string,
      grouping?: GroupingOverride
    ): Promise<Record<string, number>> => {
      const p = new URLSearchParams({ classifying_var: classifyingVar });
      if (grouping) p.set("grouping", JSON.stringify(grouping));
      return fetch(`${API_BASE}/materials/${materialId}/split-groups?${p}`)
        .then((r) => json<{ groups: Record<string, number> }>(r))
        .then((d) => d.groups);
    },
```

- [ ] **Step 2: Add the generation helper**

In `web/src/lib/charts.ts`:

```ts
/** Chart types that can draw more than one series. A pie cannot, which is why a
 * total-level pie becomes a clustered bar when split. (spec compare-groups §2) */
const MULTI_SERIES_CAPABLE = new Set<string>([
  "horizontal_bar", "vertical_bar", "line", "radar", "combo", "scatter",
  "stacked_horizontal_bar", "stacked_vertical_bar",
]);

export function supportsMultiSeries(chartType: string): boolean {
  return MULTI_SERIES_CAPABLE.has(chartType);
}

/** A comparison slide for `source`, split by `classifyingVar`.
 *
 * Clears classifying_var_2: with a banner classifier the engine REJECTS a second
 * classifier, so carrying one over would make the slide fail to render. Carries no
 * slide_title, so generating a dozen slides fires no AI title calls. */
export function makeComparisonSlide(
  source: ChartSpec,
  classifyingVar: string
): ChartSpec {
  return {
    ...source,
    slide_id: newSlideId(),
    compare_group: classifyingVar,
    classifying_var: classifyingVar,
    classifying_var_2: null,
    percent_base: "auto",
    chart_type: supportsMultiSeries(source.chart_type)
      ? source.chart_type
      : "horizontal_bar",
    slide_title: null,
  };
}

export function newSlideId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
}
```

- [ ] **Step 3: Typecheck**

Run: `cd web && npx tsc --noEmit -p tsconfig.app.json`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add web/src/lib/api.ts web/src/lib/charts.ts
git commit -m "feat(web): comparison-slide generation and the split-groups call"
```

---

### Task 4: The dialog and the selection model (spec §1.1, §1.2, §1.3, §3)

**Files:**
- Modify: `web/src/components/wizard/AddSpecialDialog.tsx`
- Modify: `web/src/components/wizard/ReportWizard.tsx`
- Modify: `web/src/components/wizard/StepSelect.tsx`

**Interfaces:**
- Consumes: `makeComparisonSlide`, `api.materials.splitGroups`.
- Produces: an `onAddComparison(classifyingVar, qids)` callback on `ReportWizard`.

- [ ] **Step 1: Make the dialog able to host a non-AI, repeatable choice**

In `AddSpecialDialog.tsx`, move the AI wording onto the three AI choices and let a
choice opt out of the once-only rule:

```tsx
// `repeatable` choices stay enabled after one has been added — comparing by Polku
// and then by gender are two legitimate sections. (spec compare-groups §1.2)
const SPECIAL_SLIDE_CHOICES: {
  type: string; label: string; description: string;
  Icon: typeof FileTextIcon; repeatable?: boolean;
}[] = [ /* …existing three, unchanged… */,
  {
    type: "compare_groups",
    label: "Compare groups",
    description:
      "One slide per question, split into the groups of a variable you choose.",
    Icon: ColumnsIcon,
    repeatable: true,
  },
];
```

Change the dialog subtitle from "Special slides are written by AI from the report's
data." to "Add a slide beyond the one-per-question defaults." and gate the disable:

```tsx
const added = existingTypes.has(type) && !repeatable;
```

Import `ColumnsIcon` from `lucide-react`.

Rename the dialog title from "Add a special slide" to "Add a slide", and the button
in `StepSelect.tsx:320` from "Add special slide" to "Add slide" — this is the
report's only add-slide entry point, and it no longer offers only special slides.

- [ ] **Step 2: Add the Compare-groups form**

Still in `AddSpecialDialog.tsx`, when `compare_groups` is picked, show the form
instead of closing. It needs `variables`, `questions`, `materialId` and `grouping`
as props, and calls `onAddComparison(classifyingVar, qids)`:

```tsx
function CompareGroupsForm({ materialId, grouping, variables, questions, onSubmit }) {
  const [clf, setClf] = useState<string>("");
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());

  // Which questions this variable actually splits — a battery belonging to one
  // study arm reports 1 group and must not be offered. (spec §1.1)
  useEffect(() => {
    if (!clf) { setCounts(null); return; }
    let live = true;
    setCounts(null);
    api.materials.splitGroups(materialId, clf, grouping).then((c) => {
      if (!live) return;
      setCounts(c);
      setPicked(new Set(questions.filter((q) => (c[q.qid] ?? 0) >= 2).map((q) => q.qid)));
    });
    return () => { live = false; };
  }, [clf, materialId, questions, grouping]);

  const splits = (qid: string) => (counts?.[qid] ?? 0) >= 2;
  return (/* select of segmentable variables; a checkbox per question, disabled
             with "only one group answered this question" when !splits(qid);
             confirm disabled until clf && picked.size */);
}
```

- [ ] **Step 3: Generate the slides**

In `ReportWizard.tsx`, beside `addSpecialSlide`:

```tsx
  // Appended AFTER the last chart slide, not at the front: a comparison section is
  // a closing section, and the front is where addSpecialSlide puts special slides.
  const addComparisonSection = useCallback(
    (classifyingVar: string, qids: string[]) => {
      mutate((d) => {
        const byRef = new Map(d.charts.map((c) => [c.question_ref, c]));
        const made = qids
          .map((qid) => byRef.get(qid))
          .filter((c): c is ChartSpec => !!c)
          .map((c) => makeComparisonSlide(c, classifyingVar));
        return { ...d, charts: normalizeSlots([...d.charts, ...made]) };
      });
    },
    [mutate]
  );
```

- [ ] **Step 4: Stop the question toggle from deleting comparison slides**

In `ReportWizard.tsx`, the toggle currently removes every chart for a question:

```tsx
d.charts.filter((c) => c.question_ref !== q.qid)
```

Change both that call and the bulk `pruneToValidRefs`/clear paths to keep marked
slides:

```tsx
// A comparison slide is not the question's primary slide — unticking the question
// must not delete it. (spec compare-groups §3)
d.charts.filter((c) => c.question_ref !== q.qid || !!c.compare_group)
```

- [ ] **Step 5: Typecheck and run the app**

Run: `cd web && npx tsc --noEmit -p tsconfig.app.json`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add web/src/components/wizard/
git commit -m "feat(web): Compare groups section in the add-slide dialog"
```

---

### Task 5: End-to-end verification on the client fixture (spec §5)

**Files:**
- Test: `tests/suite/integration/test_compare_groups.py` (create)

**Interfaces:**
- Consumes: everything above.

- [ ] **Step 1: Write the test**

Create `tests/suite/integration/test_compare_groups.py`:

```python
"""A generated comparison slide must render as a real two-group chart.
(spec 2026-08-02-compare-groups-section §5)"""
from __future__ import annotations

import dataclasses
import json
import pathlib

import pytest

from reportbuilder.api.model_loader import df_model_for_material
from reportbuilder.model.report import report_from_json
from reportbuilder.stats import engine
from reportbuilder.store.memory_client import InMemoryDataHiveClient

_STORE = pathlib.Path("work/demo-store")


def _load():
    if not (_STORE / "materials" / "mat-erisan.sav").exists():
        pytest.skip("mat-erisan not available locally")
    rep = json.loads(json.loads((_STORE / "reports.json").read_text())["rep-erisan"])
    r = report_from_json(rep)
    df, model = df_model_for_material(
        "mat-erisan", InMemoryDataHiveClient(storage_dir=str(_STORE)), rep["grouping"])
    return r, df, model


def test_a_generated_slide_has_two_groups_with_the_known_bases():
    r, df, model = _load()
    src = next(c for c in r.charts if c.question_ref == "var3")
    gen = dataclasses.replace(src, classifying_var="polku", classifying_var_2=None,
                              compare_group="polku", chart_type="horizontal_bar")
    res = engine.compute(model.question("var3"), gen, df, model)
    assert sorted(res.base_n[s] for s in res.segments if s != "Total") == [255, 256]


def test_clearing_the_second_classifier_avoids_the_banner_error():
    """A source slide that is a cross-tab would otherwise raise."""
    r, df, model = _load()
    src = next(c for c in r.charts if c.question_ref == "var3")
    crossed = dataclasses.replace(src, classifying_var="var4", classifying_var_2="var5")
    gen = dataclasses.replace(crossed, classifying_var="polku",
                              classifying_var_2=None, compare_group="polku")
    engine.compute(model.question("var3"), gen, df, model)   # must not raise


def test_the_single_arm_batteries_report_one_group():
    """The 6 questions the dialog must disable."""
    from reportbuilder.stats.engine import _classifier_masks, _drop_empty_segments

    _r, df, model = _load()

    class _S:
        classifying_var = "polku"
        classifying_var_2 = None

    masks = _classifier_masks(_S(), df, model)
    ones = 0
    for q in model.questions:
        vars_ = [model.variables[v] for v in q.variables if v in model.variables]
        if vars_ and len(_drop_empty_segments(masks, vars_, df) or {}) < 2:
            ones += 1
    assert ones >= 6
```

- [ ] **Step 2: Run it**

Run: `.venv/bin/python -m pytest tests/suite/integration/test_compare_groups.py -q -rs`
Expected: PASS (or SKIP without the fixture).

- [ ] **Step 3: Verify in the running app**

Start the stack, open `case-erisan`, click **Add special slide → Compare groups**,
choose `Polku`, confirm the six single-arm batteries are disabled, generate, and
check a generated slide renders two series.

```bash
NSIGHT_DEMO=1 NSIGHT_DEMO_DIR=work/demo-store NSIGHT_RELOAD=1 NSIGHT_PORT=8200 \
  .venv/bin/python -m reportbuilder.api.server &
cd web && npx vite --port 5173 --strictPort
```

- [ ] **Step 4: Commit**

```bash
git add tests/suite/integration/test_compare_groups.py
git commit -m "test: comparison slides render as real two-group charts"
```

---

## Self-review notes

- **Spec coverage:** §1 → Task 4. §1.1 → Tasks 2 and 4. §1.2, §1.3 → Task 4. §2 → Task 3. §3 → Tasks 1 and 4. §5 → Task 5 plus per-task tests.
- **Risk in Task 1:** an existing serde test may assert the exact key set of a serialised chart; it needs the two new keys.
- **Risk in Task 4:** the question toggle is Step 1's core interaction. Its filter appears in more than one place (single toggle, bulk clear, prune) — all must keep marked slides, or a comparison section vanishes when the author unticks a question.
- **Deliberately out of scope:** `AiPendingMap` stays keyed by `question_ref`, so a title spinner shows on both twins (spec §3, cosmetic).
