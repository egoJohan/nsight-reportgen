# Comparison Grouping — P2a Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a *comparison* (overlay several parallel questions as one radar/grouped-bar) a first-class, explicit grouping in the data model, override, engine, and suggestions — the backend the P2b workspace UI will drive.

**Architecture:** A comparison is a new `Question` kind (`"comparison"`) carrying `members` (the qids of the parallel questions it overlays). It is produced by resolving a new `comparisons` list on `GroupingOverride` *after* Tier-1 (multi/battery) resolution, so its members reference real qids. The engine routes `kind=="comparison"` to the existing (Phase 1) `_multi_comparison`/`_battery_comparison`, now able to take an EXPLICIT member list instead of only auto-detecting. `/regroup` also returns `parallel_suggestions` (question sets sharing a category set) to seed the UI.

**Tech Stack:** Python 3.13, pandas, dataclasses, FastAPI + Pydantic, pytest. Frontend: TypeScript types only (no UI in P2a).

## Global Constraints
- TDD: no production code without a failing test first. Run `.venv/bin/python -m pytest` from repo root.
- Comparison members are QIDS (Tier-1 outputs), resolved leniently: unknown/missing members are dropped, a comparison with <2 surviving members is dropped entirely (mirrors today's invalid-group handling).
- Phase 1 auto-detect (a multi/battery radar auto-overlaying parallel siblings) STAYS UNCHANGED in P2a — comparisons are additive. (Flipping auto-detect to suggestion-only is a P2b concern.)
- Do NOT commit client SAV data. Verification is local.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

## File Structure
- `src/reportbuilder/model/question.py` — add `members` field to `Question` (comparison member qids).
- `src/reportbuilder/stats/engine.py` — generalise `_multi_comparison`/`_battery_comparison` to accept explicit `members`; route `kind=="comparison"` to them; add `_comparison_common_stem` reuse of `_series_label`'s affix logic for the comparison title.
- `src/reportbuilder/ingest/grouping_override.py` — `_apply_comparisons` (resolve `comparisons` → comparison questions) called at the end of `apply_grouping_override`; `suggest_parallel_questions(model)`.
- `src/reportbuilder/api/routes_questions.py` — `ComparisonSpec` Pydantic + `comparisons` on the override model; `/regroup` returns `parallel_suggestions`.
- `web/src/lib/api.ts` — `ComparisonSpec` + `GroupingOverride.comparisons` + `ParallelSuggestion` types (serde only).

---

### Task 1: `Question.members` field

**Files:**
- Modify: `src/reportbuilder/model/question.py` (the `Question` dataclass, after `value_merges`)
- Test: `tests/rb/stats/test_engine_multi_comparison.py` (append)

**Interfaces:**
- Produces: `Question(..., members: tuple[str, ...] = ())` — member qids for a `kind=="comparison"` question; empty for all other kinds.

- [ ] **Step 1: Write the failing test**
```python
def test_question_carries_comparison_members():
    from reportbuilder.model.question import Question
    q = Question(qid="compare-x", kind="comparison", variables=("a", "b"),
                 text="X", members=("adj1", "adj2"))
    assert q.members == ("adj1", "adj2")
    # default is empty for ordinary questions
    assert Question(qid="q", kind="single", variables=("a",), text="Q").members == ()
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/python -m pytest tests/rb/stats/test_engine_multi_comparison.py::test_question_carries_comparison_members -v`
Expected: FAIL — `TypeError: Question.__init__() got an unexpected keyword argument 'members'`

- [ ] **Step 3: Add the field**
In `src/reportbuilder/model/question.py`, immediately after the `value_merges` field of `Question`:
```python
    # Comparison groups (Tier 2): the QIDS of the parallel questions this comparison
    # overlays as series (radar / grouped-bar). Empty for every non-comparison question.
    members: tuple[str, ...] = ()
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/bin/python -m pytest tests/rb/stats/test_engine_multi_comparison.py::test_question_carries_comparison_members -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/reportbuilder/model/question.py tests/rb/stats/test_engine_multi_comparison.py
git commit -m "feat(model): Question.members — comparison member qids

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `_multi_comparison` accepts an explicit member list

**Files:**
- Modify: `src/reportbuilder/stats/engine.py` — `_multi_comparison` signature + first line.
- Test: `tests/suite/unit/stats/test_engine_multi_comparison.py` (append)

**Interfaces:**
- Consumes: `_parallel_questions`, `_series_label`, `multi_base`, `pct`, `count_value` (existing).
- Produces: `_multi_comparison(question, spec, data, model, members=None)` — when `members` (a `list[Question]`) is given, those are the series; when `None`, auto-detect via `_parallel_questions` (Phase 1 behaviour, unchanged).

- [ ] **Step 1: Write the failing test**
```python
def test_multi_comparison_explicit_members_subset():
    # Reuse the two-adjective fixture; pass ONLY Rohkea explicitly -> single series.
    model, q_rohkea, q_luot, df = _multi_model()
    r = engine._multi_comparison(q_rohkea, _spec(chart_type="radar"), df, model,
                                 members=[q_rohkea])
    assert set(r.segments) == {"Rohkea"}
    assert r.categories == ("IS", "IL", "HS")
```
(Uses the existing `_multi_model` / `_spec` helpers already in this file.)

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_engine_multi_comparison.py::test_multi_comparison_explicit_members_subset -v`
Expected: FAIL — `TypeError: _multi_comparison() got an unexpected keyword argument 'members'`

- [ ] **Step 3: Add the `members` param**
In `src/reportbuilder/stats/engine.py`, change the `_multi_comparison` signature and its first body line:
```python
def _multi_comparison(question: Question, spec: ChartSpec, data: pd.DataFrame,
                      model: QuestionModel, members: list[Question] | None = None) -> SeriesResult:
    """... (existing docstring) ..."""
    sibs = members if members is not None else _parallel_questions(question, model)
```
(Leave the rest of the function body unchanged — it already iterates `sibs`.)
Note: with a single-element `members`, `_series_label` returns via its `len<2` branch (`_entity_label`); for a lone multi that yields the question's own label, which is acceptable for the subset case.

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_engine_multi_comparison.py -v`
Expected: PASS (new test + all Phase 1 tests still green)

- [ ] **Step 5: Commit**
```bash
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_engine_multi_comparison.py
git commit -m "feat(stats): _multi_comparison accepts an explicit member list

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `_battery_comparison` accepts an explicit member list

**Files:**
- Modify: `src/reportbuilder/stats/engine.py` — `_battery_comparison` signature + its `sibs =` line.
- Test: `tests/suite/unit/stats/test_engine_battery.py` (append)

**Interfaces:**
- Produces: `_battery_comparison(question, spec, data, model, members=None)` — explicit members override the `_parallel_questions` auto-detect.

- [ ] **Step 1: Write the failing test**
```python
def test_battery_comparison_explicit_members():
    # Two parallel batteries (same attributes) -> pass both explicitly.
    from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
    def rv(n, l): return Variable(name=n, label=l, measurement="scale",
        value_labels=tuple(ValueLabel(float(i), str(i)) for i in range(1, 6)),
        missing_values=frozenset())
    import pandas as pd
    vars_ = {"a1": rv("a1", "Nopeus"), "a2": rv("a2", "Laatu"),
             "b1": rv("b1", "Nopeus"), "b2": rv("b2", "Laatu")}
    qa = Question(qid="qa", kind="battery", variables=("a1", "a2"), text="Attendo — Arvio")
    qb = Question(qid="qb", kind="battery", variables=("b1", "b2"), text="Esperi — Arvio")
    model = QuestionModel(variables=vars_, questions=[qa, qb])
    df = pd.DataFrame({"a1": [5, 4], "a2": [3, 3], "b1": [2, 2], "b2": [4, 4]})
    r = engine._battery_comparison(qa, _spec(chart_type="radar"), df, model, members=[qa, qb])
    assert r.categories == ("Nopeus", "Laatu")
    assert set(r.segments) == {"Attendo", "Esperi"}
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_engine_battery.py::test_battery_comparison_explicit_members -v`
Expected: FAIL — `TypeError: _battery_comparison() got an unexpected keyword argument 'members'`

- [ ] **Step 3: Add the `members` param + use `_series_label` for entity labels**
In `_battery_comparison`, change the signature and the `sibs =`/entity-label lines:
```python
def _battery_comparison(question: Question, spec: ChartSpec, data: pd.DataFrame,
                        model: QuestionModel, members: list[Question] | None = None) -> SeriesResult:
    """... existing docstring ..."""
    sibs = members if members is not None else _parallel_questions(question, model)
```
Then change the per-entity label line inside the `for q in sibs:` loop from `ent = _entity_label(q)` to `ent = _series_label(q, sibs)` (unifies with the multi path; for "Attendo — Arvio"/"Esperi — Arvio" this yields "Attendo"/"Esperi" via the common-suffix strip).

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_engine_battery.py tests/test_golden_attendo.py -v -m "not live and not demo"`
Expected: PASS — new test green AND the Attendo golden deck unchanged (verifies `_series_label` matches the old `_entity_label` output on real data). If a golden diff appears, inspect it; only update the golden if the new label is genuinely correct.

- [ ] **Step 5: Commit**
```bash
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_engine_battery.py
git commit -m "feat(stats): _battery_comparison explicit members + unified series label

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Engine routes `kind=="comparison"` to the overlay

**Files:**
- Modify: `src/reportbuilder/stats/engine.py` — top of `compute` (before the battery branch).
- Test: `tests/suite/unit/stats/test_engine_multi_comparison.py` (append)

**Interfaces:**
- Consumes: `Question.members` (Task 1), `_multi_comparison`/`_battery_comparison` (Tasks 2/3), `model.question(qid)`.
- Produces: a `compute` path — for `question.kind == "comparison"`, resolve `question.members` to Questions and overlay them; member kind (`multi`/`battery`) picks the builder. Members not in the model are dropped; <2 survivors → falls back to the first member's normal chart (never crash).

- [ ] **Step 1: Write the failing test**
```python
def test_compute_routes_comparison_question():
    model, q_rohkea, q_luot, df = _multi_model()
    comp = Question(qid="compare-brandi", kind="comparison",
                    variables=q_rohkea.variables + q_luot.variables,
                    text="Brändimielikuva", members=("rohkea", "luot"))
    model.questions.append(comp)
    r = engine.compute(comp, _spec(chart_type="radar"), df, model)
    assert set(r.segments) == {"Rohkea", "Luotettava"}
    assert r.categories == ("IS", "IL", "HS")

def test_compute_comparison_not_radar_only():
    # A comparison is a grid; a grouped/vertical bar yields the SAME multi-series result.
    model, q_rohkea, q_luot, df = _multi_model()
    comp = Question(qid="compare-brandi", kind="comparison",
                    variables=q_rohkea.variables + q_luot.variables,
                    text="Brändimielikuva", members=("rohkea", "luot"))
    model.questions.append(comp)
    r = engine.compute(comp, _spec(chart_type="vertical_bar"), df, model)
    assert set(r.segments) == {"Rohkea", "Luotettava"}   # not radar-only
    assert r.categories == ("IS", "IL", "HS")
```
(`Question` is already imported in this test module.)

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_engine_multi_comparison.py::test_compute_routes_comparison_question -v`
Expected: FAIL — a `comparison`-kind question currently falls through to `_single`/`_multi`, so segments won't be `{Rohkea, Luotettava}` (KeyError or wrong shape).

- [ ] **Step 3: Add the routing branch**
In `compute`, immediately after the `wordcloud`/text guards and BEFORE `if question.kind == "battery":`, add:
```python
    if question.kind == "comparison":
        members = [model.question(q) for q in question.members if _has_question(model, q)]
        if len(members) >= 2:
            builder = _battery_comparison if members[0].kind == "battery" else _multi_comparison
            return builder(members[0], spec, data, model, members=members)
        if members:                       # degenerate: 1 surviving member → its normal chart
            return compute(members[0], spec, data, model)
        raise ValueError("comparison has no resolvable members")
```
Add this helper near `_parallel_questions`:
```python
def _has_question(model: QuestionModel, qid: str) -> bool:
    return any(q.qid == qid for q in model.questions)
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/bin/python -m pytest tests/suite/unit/stats/test_engine_multi_comparison.py -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/reportbuilder/stats/engine.py tests/suite/unit/stats/test_engine_multi_comparison.py
git commit -m "feat(stats): route kind=comparison to the overlay builder

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Override resolves `comparisons` into comparison questions

**Files:**
- Modify: `src/reportbuilder/ingest/grouping_override.py` — add `_apply_comparisons` + call it at the end of `apply_grouping_override`.
- Test: `tests/suite/unit/ingest/test_grouping_override.py` (create if absent; else append)

**Interfaces:**
- Consumes: the resolved Tier-1 model `m`; `override["comparisons"]` = `[{members: [qid], render: str, label?: str}]`.
- Produces: `_apply_comparisons(m: QuestionModel, comparisons: list[dict]) -> QuestionModel` — appends one `kind=="comparison"` Question per valid spec (≥2 members that exist in `m`); title = spec label or the common stem of member texts; qid = `"compare-" + _slug(title)`. Called last in `apply_grouping_override`.

- [ ] **Step 1: Write the failing test**
```python
import pandas as pd
from reportbuilder.model.question import ValueLabel, Variable, Question, QuestionModel
from reportbuilder.ingest.grouping_override import apply_grouping_override

def _binary(n, l):
    return Variable(name=n, label=l, measurement="categorical",
                    value_labels=(ValueLabel(0.0, "Ei"), ValueLabel(1.0, "Kyllä")),
                    missing_values=frozenset())

def test_apply_comparisons_builds_comparison_question():
    vars_ = {"r_is": _binary("r_is", "IS"), "r_il": _binary("r_il", "IL"),
             "l_is": _binary("l_is", "IS"), "l_il": _binary("l_il", "IL")}
    qs = [Question(qid="rohkea", kind="multi", variables=("r_is", "r_il"), text="-Rohkea"),
          Question(qid="luot", kind="multi", variables=("l_is", "l_il"), text="-Luotettava")]
    model = QuestionModel(variables=vars_, questions=qs)
    override = {"groups": [], "singles": [],
                "comparisons": [{"members": ["rohkea", "luot"], "render": "radar",
                                 "label": "Brändimielikuva"}]}
    m = apply_grouping_override(model, override)
    comp = [q for q in m.questions if q.kind == "comparison"]
    assert len(comp) == 1
    assert comp[0].members == ("rohkea", "luot")
    assert comp[0].text == "Brändimielikuva"

def test_apply_comparisons_drops_when_under_two_valid_members():
    vars_ = {"r_is": _binary("r_is", "IS")}
    qs = [Question(qid="rohkea", kind="multi", variables=("r_is",), text="-Rohkea")]
    model = QuestionModel(variables=vars_, questions=qs)
    override = {"comparisons": [{"members": ["rohkea", "ghost"], "render": "radar"}]}
    m = apply_grouping_override(model, override)
    assert not [q for q in m.questions if q.kind == "comparison"]
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_grouping_override.py -k comparisons -v`
Expected: FAIL — no comparison question is produced (`apply_grouping_override` ignores `comparisons`).

- [ ] **Step 3: Implement `_apply_comparisons` + wire it in**
Add to `src/reportbuilder/ingest/grouping_override.py` (reuse the module's existing `_slug` if present; otherwise add the small slugger shown):
```python
def _common_stem(texts: list[str]) -> str:
    """Shortest distinguishing-free shared label for a comparison title: the common
    prefix of the member texts, trimmed to a separator; falls back to the first text."""
    import os
    if not texts:
        return "Vertailu"
    pre = os.path.commonprefix([t.strip() for t in texts]).strip(" -–—:·,;/|")
    return pre or texts[0].strip()

def _comp_slug(text: str) -> str:
    import re
    return "compare-" + (re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x")

def _apply_comparisons(model: QuestionModel, comparisons: list) -> QuestionModel:
    """Resolve Tier-2 comparison specs into kind=='comparison' questions. Members are
    qids that must exist in the (already Tier-1-resolved) model; a spec with <2 valid
    members is dropped (lenient)."""
    if not comparisons:
        return model
    have = {q.qid: q for q in model.questions}
    extra: list[Question] = []
    for c in comparisons:
        member_qids = [q for q in (c.get("members") or []) if q in have]
        if len(member_qids) < 2:
            continue
        member_qs = [have[q] for q in member_qids]
        title = (c.get("label") or "").strip() or _common_stem([q.text for q in member_qs])
        variables = tuple(v for mq in member_qs for v in mq.variables)
        extra.append(Question(qid=_comp_slug(title), kind="comparison",
                              variables=variables, text=title, members=tuple(member_qids)))
    if not extra:
        return model
    return QuestionModel(variables=model.variables, questions=list(model.questions) + extra)
```
Then, in `apply_grouping_override`, change the final `return m` to:
```python
    m = _apply_comparisons(m, override.get("comparisons", []) or [])
    return m
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_grouping_override.py -k comparisons -v`
Expected: PASS

- [ ] **Step 5: Commit**
```bash
git add src/reportbuilder/ingest/grouping_override.py tests/suite/unit/ingest/test_grouping_override.py
git commit -m "feat(ingest): resolve override comparisons into comparison questions

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `suggest_parallel_questions` + `/regroup` returns them

**Files:**
- Modify: `src/reportbuilder/ingest/grouping_override.py` — add `suggest_parallel_questions`.
- Modify: `src/reportbuilder/api/routes_questions.py` — `ComparisonSpec` Pydantic + `comparisons` on the override model; `/regroup` returns `parallel_suggestions`.
- Test: `tests/suite/unit/ingest/test_grouping_override.py` + `tests/rb/api/` regroup test (append to the existing regroup test file).

**Interfaces:**
- Produces: `suggest_parallel_questions(model) -> list[dict]` — one entry per group of ≥2 questions of the same kind sharing an exact category label-set: `{"qids": [...], "labels": [...], "kind": "multi"|"battery"}`.
- Produces: `/regroup` response gains `parallel_suggestions: list[...]`; the override request model accepts `comparisons`.

- [ ] **Step 1: Write the failing test**
```python
def test_suggest_parallel_questions_groups_by_category_set():
    from reportbuilder.ingest.grouping_override import suggest_parallel_questions
    vars_ = {"r_is": _binary("r_is", "IS"), "r_il": _binary("r_il", "IL"),
             "l_is": _binary("l_is", "IS"), "l_il": _binary("l_il", "IL"),
             "x_a": _binary("x_a", "A"), "x_b": _binary("x_b", "B")}
    qs = [Question(qid="rohkea", kind="multi", variables=("r_is", "r_il"), text="-Rohkea"),
          Question(qid="luot", kind="multi", variables=("l_is", "l_il"), text="-Luotettava"),
          Question(qid="other", kind="multi", variables=("x_a", "x_b"), text="Muu")]
    model = QuestionModel(variables=vars_, questions=qs)
    sugg = suggest_parallel_questions(model)
    # exactly one group (Rohkea+Luotettava share {IS,IL}); 'other' has a different set
    assert len(sugg) == 1
    assert set(sugg[0]["qids"]) == {"rohkea", "luot"}
```

- [ ] **Step 2: Run test to verify it fails**
Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_grouping_override.py::test_suggest_parallel_questions_groups_by_category_set -v`
Expected: FAIL — `ImportError: cannot import name 'suggest_parallel_questions'`

- [ ] **Step 3: Implement the suggester**
Add to `src/reportbuilder/ingest/grouping_override.py`:
```python
def suggest_parallel_questions(model: QuestionModel) -> list[dict]:
    """Sets of >=2 questions of the same kind sharing an EXACT category label-set — the
    parallel questions a comparison would overlay. Ordered by first appearance."""
    from collections import OrderedDict
    buckets: "OrderedDict[tuple, list]" = OrderedDict()
    for q in model.questions:
        if q.kind not in ("multi", "battery"):
            continue
        sig = (q.kind, frozenset(model.variables[v].label for v in q.variables))
        buckets.setdefault(sig, []).append(q)
    out = []
    for (kind, _sig), qs in buckets.items():
        if len(qs) >= 2:
            out.append({"kind": kind, "qids": [q.qid for q in qs],
                        "labels": [q.text for q in qs]})
    return out
```

- [ ] **Step 4: Run test to verify it passes**
Run: `.venv/bin/python -m pytest tests/suite/unit/ingest/test_grouping_override.py::test_suggest_parallel_questions_groups_by_category_set -v`
Expected: PASS

- [ ] **Step 5: Wire into the API — `ComparisonSpec` + `/regroup` payload**
In `src/reportbuilder/api/routes_questions.py`: (a) beside the existing `GroupSpec`/`GroupingOverride` Pydantic models (around lines 635-645) add:
```python
class ComparisonSpec(BaseModel):
    members: list[str]
    label: str | None = None
```
(No `render` — the chart type radar/grouped-bar is chosen in the Design phase like any chart,
via the suitability picker, not stored on the comparison.)
and add `comparisons: list[ComparisonSpec] = []` to the `GroupingOverride` request model. (b) In the `regroup` handler, after `suggestions = suggest_scale_batteries(model)`, add:
```python
    from reportbuilder.ingest.grouping_override import suggest_parallel_questions
    parallel = suggest_parallel_questions(model)
```
and include `"parallel_suggestions": parallel` in the returned dict. Ensure `override.model_dump()` (or the dict already passed) carries `comparisons` through to `apply_grouping_override`.

- [ ] **Step 6: Write + run the API test**
Append to the existing regroup route test file (find it: `grep -rl "regroup" tests/rb/api tests/suite/integration/api`). Test that POSTing an override with a `comparisons` entry returns a question with `kind=="comparison"` and that `parallel_suggestions` is present:
```python
def test_regroup_returns_parallel_suggestions_and_comparison(client, material_with_parallel_multis):
    # material fixture has >=2 multis sharing an option set
    body = {"groups": [], "singles": [],
            "comparisons": [{"members": [<qid1>, <qid2>], "render": "radar", "label": "Vertailu"}]}
    r = client.post(f"/materials/{mid}/regroup", json=body)
    assert r.status_code == 200
    data = r.json()
    assert any(q["kind"] == "comparison" for q in data["questions"])
    assert "parallel_suggestions" in data
```
Run: `.venv/bin/python -m pytest <that test file> -v`
Expected: PASS. (If no suitable material fixture exists, build the model inline via the DuckDB test seam used by the other regroup tests — mirror their fixture.)

- [ ] **Step 7: Commit**
```bash
git add src/reportbuilder/ingest/grouping_override.py src/reportbuilder/api/routes_questions.py tests/
git commit -m "feat(api): parallel-question suggestions + comparisons in /regroup

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Frontend serde types (no UI)

**Files:**
- Modify: `web/src/lib/api.ts` — near `GroupSpec`/`GroupingOverride`/`BatterySuggestion` (lines 330-346).
- Test: `cd web && npx tsc -b` (type-check only; no runtime UI in P2a).

**Interfaces:**
- Produces: `ComparisonSpec`, `GroupingOverride.comparisons?`, `ParallelSuggestion` — consumed by the P2b workspace.

- [ ] **Step 1: Add the types**
```ts
export interface ComparisonSpec {
  members: string[];                 // qids of the parallel questions to overlay
  label?: string | null;             // chart type is a Design-phase choice, not stored here
}
export interface ParallelSuggestion {
  kind: "multi" | "battery";
  qids: string[];
  labels: string[];
}
```
and add to `GroupingOverride`: `comparisons?: ComparisonSpec[];`

- [ ] **Step 2: Type-check**
Run: `cd web && npx tsc -b`
Expected: exit 0 (no type errors).

- [ ] **Step 3: Commit**
```bash
git add web/src/lib/api.ts
git commit -m "feat(web): ComparisonSpec / ParallelSuggestion serde types

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Full-tree regression gate

**Files:** none (verification task).

- [ ] **Step 1: Run the full backend tree**
Run: `.venv/bin/python -m pytest tests -q -m "not live and not demo"`
Expected: all pass (baseline was 1701). Investigate any failure; the highest-risk area is the `_series_label`-for-battery change (Task 3) touching the Attendo golden — if a golden changed, confirm the new entity label is correct before updating it.

- [ ] **Step 2: Commit any golden updates (only if justified)**
```bash
git add tests/ && git commit -m "test: update goldens for unified comparison series label

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage** (against `2026-07-03-grouping-workspace-ui-rework-design.md`, Data-model section):
- `ComparisonSpec` (members/render/label) → Task 5 (resolution) + Task 7 (TS). ✓
- Resolution order (Tier 1 then comparisons; lenient drop) → Task 5. ✓
- Engine renders a comparison (radar/grouped-bar from members) → Tasks 2-4. ✓
- `parallel_suggestions` from `/regroup` → Task 6. ✓
- Qid stability of members → members are looked up by qid in Task 4/5; battery qids are stable slugs, multi qids stable per the existing model — noted as a risk below.
- Awareness UI (Structure rail, Changes log, Impact counter, where-it-lands, preview) → NOT in P2a; these are P2b (separate plan). This plan deliberately covers only the data/engine spine.

**Type consistency:** `members` (tuple[str,...]) on `Question` (Task 1) is read in Tasks 4/5; `_multi_comparison`/`_battery_comparison` gain the same `members=None` kwarg (Tasks 2/3) called positionally-by-keyword in Task 4; `ComparisonSpec.render` is `"radar"|"grouped_bar"` in both Python (str) and TS (Task 7). Consistent.

**Placeholder scan:** the Task 6 API test uses `<qid1>`/`material_with_parallel_multis` placeholders because the exact regroup-test fixture must be read at implementation time — Step 6 instructs mirroring the existing regroup fixture. This is the one deliberately-deferred detail; flagged, not hidden.

## Risks / notes for the implementer
- **Phase 1 auto-detect stays.** A plain multi/battery radar still auto-overlays parallel siblings (Phase 1). Comparison questions are ADDITIVE. Making auto-detect suggestion-only (the escape hatch) is P2b, once the workspace can author explicit comparisons.
- **Multi qid stability.** Comparison members reference multi/battery qids. Battery qids are stable slugs; confirm multi qids don't change when unrelated groups are edited (they are derived from members). If they can drift, P2b must re-point comparison members on edit.
- **Grouped-bar rendering** of a comparison (render=="grouped_bar") reuses the clustered-bar renderer on the multi-series result — verify visually in P2b; P2a only guarantees the SeriesResult shape.
