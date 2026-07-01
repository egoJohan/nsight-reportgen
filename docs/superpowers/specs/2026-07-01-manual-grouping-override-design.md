# Manual variable grouping (single ↔ multi ↔ battery) — design

**Date:** 2026-07-01
**Status:** approved (design), pending implementation plan
**Phase:** 1 of 2 (Phase 1 = combine / split / fix-auto; Phase 2 = manual battery)

## Problem

A customer (a research professional) can't combine several variables into a
multi-response question, or split one back apart. The engine **auto-detects**
multi/battery groups (`enrich_model`), but there is **no manual override**: no UI,
and the backend `PUT /materials/{id}/grouping` is only a *stateless preview* that
"Does NOT persist. Persistence … DEFERRED to Phase 4." This spec lands that
persistence plus the UI.

## Goal

Let a user, per material, in the case **Questions** section:
- **Combine** ≥2 (non-scale) variables into one **multi** question.
- **Split / ungroup** a multi (auto- or manually-made) back into its singles.
- **Fix an auto-detected group** (correct its membership).
- (**Phase 2**) define a **battery** group by hand.

The manual choice **persists server-side** and flows into every downstream view
(questions list, summaries, charts, rendered decks) — visible to any user/device,
consistent with the case-state-server-side work.

## Non-goals (this phase)

Manual **battery** creation (Phase 2). Cross-material grouping. Changing
auto-detection heuristics. Any change to the stats/render engines beyond feeding
them the reshaped model.

## Existing seams (build on these)

- `reportbuilder.ingest.sav_reader.read_sav(path)` → raw single-question model.
- `reportbuilder.ingest.multi_group`: `suggest_multi_groups`, `apply_groups`, `enrich_model` (= multi then battery auto-detect).
- `reportbuilder.ingest.battery_group`: `suggest_batteries`, `apply_batteries`.
- `reportbuilder.api.routes_questions.load_model_for_material(material_id, client)` (= `enrich_model(read_sav)`) — the model-load seam the question endpoints use. `_load_df_model` is its df-returning sibling. `routes_render` and `routes_ai` currently call `enrich_model` **directly** — see §4 (consistency).
- Existing stateless `PUT /materials/{id}/grouping` (`GroupingRequest{variables, kind}`) — preview only.
- Store persistence pattern: the Task-#5 `report_meta.json` shows how to add a persisted, per-key JSON map to `InMemoryDataHiveClient` (atomic write, tolerant load, restart-safe).

## 1. Data model — the grouping override

One override **per material**, a small JSON object:

```json
{
  "groups":  [ { "kind": "multi", "variables": ["v10O1", "v10O2"], "label": "Brand awareness" } ],
  "singles": [ "v20O1", "v20O2" ]
}
```

- `groups`: explicit manual groups. `kind` ∈ `"multi"` (Phase 1); `"battery"` added in Phase 2 (with extra scale/subject fields). `label` optional (display name; defaults to the derived group text).
- `singles`: variables **forced back to single** — the record of a split/ungroup, so auto-detection won't re-group them.
- Absent / `{}` → behaves exactly as today (pure auto-detection).

## 2. Composition — how manual overrides combine with auto-detection

New pure function `reportbuilder.ingest.grouping_override.apply_grouping_override(raw_model, override) -> QuestionModel`:

1. Collect `manual_members` = every var in `override.groups`, and `forced_singles` = `set(override.singles)`.
2. **Apply the manual groups** (`apply_groups` for `multi`).
3. Run auto-detection (`suggest_multi_groups`, `suggest_batteries`) but **drop any suggested group that includes a var in `manual_members ∪ forced_singles`**, then apply the survivors.
4. Everything else stays as auto-detected / single.

**Rule: manual wins; forced singles stay single; auto fills the gaps.** Validation
(reuse today's rules): a multi group needs ≥2 known, non-scale variables; unknown
or scale members → 422.

The three operations reduce to edits of this object:
- **Combine** → append a `{kind:"multi", variables}` to `groups`.
- **Split / ungroup** → remove the group (if manual) and add its members to `singles` (so an auto group won't reclaim them).
- **Fix auto-group** → add a corrected `{kind:"multi", variables}` (it supersedes the auto one for those vars).

## 3. Persistence + API

Store (per material), mirroring `report_meta`:
- `InMemoryDataHiveClient.save_material_config(material_id, config_json)` / `load_material_config(material_id) -> str | None`, persisted to `material_config.json` (atomic, tolerant, restart-safe; cleared on `delete_case` cascade for that case's materials).
- Real `DataHiveClient`: `save_material_config` / `load_material_config` against an assumed datahive material-metadata endpoint — **flagged for verification** (staging runs the demo client, as in Task #5).

API (in `routes_questions`):
- `GET /materials/{id}/grouping` → `{ "override": {groups, singles} }` (empty object when unset).
- `PUT /materials/{id}/grouping` → validate + persist the full override; returns the resulting question list (so the UI can refresh). Replaces the stateless-preview role; the same validation (≥2 vars, non-scale, known) applies and returns 422 on violation.

## 4. Applying the override everywhere (consistency)

The override must reshape the model at **every** material-model load site, or a
report built on a manual group wouldn't render it. Centralize: `load_model_for_material`
and `_load_df_model` (questions) apply the override, and **`routes_render` and
`routes_ai` are refactored to load through the same override-aware helper** instead
of calling `enrich_model` directly. Net: one place builds a material's model =
`apply_grouping_override(read_sav(...), load_material_config(...))`.

## 5. UI — "Manage grouping" dialog

- **Entry:** a "Manage grouping" button in the **Questions** section header (`DataTab`, beside "Replace file").
- **Dialog** (`ManageGroupingDialog`):
  - **Left** — the groupable-variable pool (non-scale) from `GET /materials/{id}/variables`, with a **"show all"** toggle to reveal hidden/paradata vars (the pool ≠ the visible question rows).
  - **Right** — group cards (multi/battery), each with members + an **Ungroup/Split** action; auto-detected groups show an "auto" tag and are editable. A **"＋ New multi group"** builds one from the checked pool variables.
  - **Save** → `PUT /materials/{id}/grouping`, then invalidate the questions query so the list + Status column reflect the new shape.
- **api.ts / queries.ts:** `getGrouping` / `putGrouping` + a `useGrouping` hook; invalidate `questions` (and `variables`) on save.

## 6. Testing

- Backend **TDD** (suite):
  - `apply_grouping_override`: combine, split (auto + manual), fix-auto, manual-wins-over-auto, forced-singles-not-regrouped, empty override == `enrich_model`, validation (unknown/scale/<2 → error).
  - Store: `save/load_material_config` round-trip + persistence across restart + cascade on `delete_case`.
  - API: `GET`/`PUT /grouping` happy paths + 422s; and that a report built on a manual multi renders it (model reshaped through the centralized loader).
- Frontend: `tsc -b` + `npm run build`; manual check in the local demo app.

## 7. Phasing

- **Phase 1 (this spec):** override model + composition + persistence + endpoints + centralized loader + the dialog for combine / split / fix-auto (multi only).
- **Phase 2:** manual **battery** — extend `groups[].kind = "battery"` with the shared rating-scale + subject/label capture, engine already renders batteries.

## 8. Store portability & datahive readiness

The design is intentionally **store-agnostic above the client interface** — routes,
contracts, frontend, and `apply_grouping_override` are reused verbatim when the
backend moves from the demo store to real datahive. Only the **client adapter
methods** differ, and those are the pieces to verify against the live datahive:

| Concern | Demo store (done) | Real datahive (to verify) |
|---|---|---|
| `list_materials` / `list_reports` | `material_meta` / `report_meta` | assumed `GET /projects/{case}/blobs` \| `/docs` — confirm shape/paths |
| report → case link | `report_meta` tagging | **native** — docs already live under `/projects/{case}/docs` (no tagging) |
| grouping override storage | `material_config.json` keyed by material_id | **needs a datahive home** for per-material config; if none, store as a case-scoped doc (needs a material→case lookup) |

Action: keep the **client method contract** the single source of truth; the demo
client is the reference implementation (and what staging runs today). Before
cutting over to datahive, run a short **verification spike** confirming each real
`DataHiveClient` method against the actual API and adjust the adapter bodies only —
no route/UI/logic changes expected. The only item that could need datahive-side
work is per-material config storage (item 3).

## Risks / notes

- **Consistency refactor (§4)** is the load-bearing part: miss a load site and a manual group silently won't render there. The plan must enumerate and cover every `enrich_model` caller.
- **Real-datahive persistence** of the material config is an assumed contract (verify later); staging is demo mode so it's unaffected now.
- **Ambiguous labels:** a manual group's display name defaults to the engine's derived group text unless `label` is set.
