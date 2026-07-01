# nSight Backend — Comprehensive Test Suite Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan milestone-by-milestone. Steps use checkbox (`- [ ]`) tracking.

**Goal:** A fresh, ultra-extensive, deterministic-by-default test suite covering the whole nSight **backend** product (`src/reportbuilder` + the `src/nsight` AI client) across four layers — **unit, integration, e2e, and agentic** — runnable entirely **locally**, alongside (not replacing) the existing `tests/rb` suite.

**Architecture:** The backend is a layered pipeline: **ingest** (SAV → model) → **stats engine** (model+data → `SeriesResult`) → **render** (image matplotlib / native python-pptx) → **export** (PPTX/PDF) → **FastAPI** surface → **egoHive AI** features. Each layer has a clean, mockable seam, so the suite tests each in isolation (unit), in composition (integration), through the HTTP surface end-to-end (e2e), and exercises the LLM boundary both mocked (deterministic) and live-gated (real local egoHive).

**Tech Stack:** Python 3.13, pytest (+pytest-asyncio, `asyncio_mode=auto`), FastAPI `TestClient`, pandas, matplotlib(Agg), python-pptx, Pillow, duckdb, pyreadstat, httpx `MockTransport`. Interpreter: `.venv/bin/python`.

---

## Global Constraints

- **LOCAL ONLY — never staging.** Every test and command runs against the local checkout. No live datahive, no `nsight.egohive.ai`, no deploy. The only "live" externals a test may touch are a **locally-running egoHive** (agentic live group) and locally-installed **soffice/poppler** (export group) — both skip-gated.
- **Fresh, isolated tree.** All new tests live under **`tests/suite/`**. The existing `tests/rb` tree is left untouched. Overlap with existing coverage is acceptable (the goal is exhaustive coverage, per decision).
- **Deterministic by default.** The standard suite (`pytest tests/suite`) makes **no network calls** and does **not** require soffice. LLM/egoHive is mocked; datahive is an injected `Mock` or `InMemoryDataHiveClient`; anything needing soffice/poppler or a live backend is behind a marker/skip-gate.
- **Seams (canonical):**
  - DataHive → inject via `create_app(client=...)` (`app.dependency_overrides[get_client]`). Use `Mock(spec=DataHiveClient)` or a real `InMemoryDataHiveClient`.
  - egoHive/LLM → monkeypatch `reportbuilder.api.routes_ai.egohive_chat` (module-level, looked up at call time), OR pass a fake `chat=` directly into `reportbuilder.ai.text.*`. For client internals, monkeypatch `urllib.request.urlopen`.
  - SAV bytes → `reportbuilder.testing.fixtures.synthetic_sav_bytes()` / `synthetic_sav(tmp_path)`.
- **Markers & gating** (register any new ones in `pyproject.toml`):
  - *(none)* → deterministic standard suite (unit, integration, mocked-agentic, image-render e2e).
  - `@pytest.mark.demo` → local-fs `InMemoryDataHiveClient` (NSIGHT_DEMO=1); auto-skips unless `NSIGHT_DEMO=1`. Real-SAV e2e.
  - `@pytest.mark.export` **(new)** → needs soffice/poppler; skips when absent. PPTX→PDF→PNG paths.
  - `@pytest.mark.live` → real local egoHive; self-skips on `EgoHiveError`. Agentic live group.
- **IPR.** Real client SAVs are read only from the gitignored `tests/rb/e2e/data/sav/` (or tracked `input/`); never copied into a tracked path, never committed.
- **Determinism hygiene.** No wall-clock/random dependence in assertions; wordcloud/top-N ordering is already deterministic (count desc, tie by label). Matplotlib uses Agg (headless).

---

## Directory Layout (fresh suite)

```
tests/suite/
  conftest.py                 # shared fixtures: apps, clients, canned chat, sav bytes, ctx builders
  unit/
    ingest/    test_sav_helpers.py test_curation.py test_multi_group.py test_battery_group.py test_enrich_model.py
    stats/     test_statistics.py test_base_rules.py test_aggregate.py test_sorting.py test_series.py
               test_engine_single.py test_engine_multi_summary.py test_engine_battery.py
               test_engine_wordcloud_combo.py test_engine_helpers.py
    model/     test_question_model.py test_report_serde.py
    render/    test_config_schema.py test_plugin_registry.py test_suitability_matrix.py
               test_shape.py test_mpl_helpers.py
    ai/        test_text_prompts.py test_text_parsing.py test_reference.py test_egohive_client.py
  integration/
    render/    test_image_matrix.py test_native_matrix.py test_deck_assembly.py test_empty_degrade.py
    export/    test_pptx_build.py test_export_soffice.py            # export → @pytest.mark.export
    api/       test_health_and_errors.py test_cases_crud.py test_materials.py test_questions.py
               test_reports_crud.py test_render_routes.py test_preview_chart.py
    store/     test_memory_client.py test_datahive_rest.py
  agentic/
    test_ai_routes_mocked.py    # deterministic, monkeypatched egohive_chat
    test_ai_text_orchestration.py
    test_ai_live.py             # @pytest.mark.live
  e2e/
    test_pipeline_image.py                 # soffice-free full pipeline (synthetic)
    test_pipeline_export.py                # @pytest.mark.export full pipeline → PDF
    test_api_full_chain_memory.py          # in-memory client through the whole API (soffice-free parts)
    test_demo_real_savs.py                 # @pytest.mark.demo, the three client SAVs
```

---

## Layer Matrices

### UNIT (pure functions, no I/O beyond reading a temp SAV)

**ingest** — `test_sav_helpers.py`: `_slug`, `_measurement` (scale vs ordinal/nominal→categorical), `_is_text_variable` (>50% non-numeric), `_user_missing` (point vs span→every int, tuple vs dict), `sav_file_label` (label / None / never-raises). `test_curation.py`: `_is_metadata` (name/label exact+prefix, never substring — "Employment Status" NOT metadata), `_is_constant_marker`, `_is_unlabeled_helper`. `test_multi_group.py`: `suggest_multi_groups` (O-pattern ≥2, binary prefix ≥2, scale excluded), `apply_groups` (multi qid/text, option-label rewrite), `_shared_question` thresholds (≥20 chars & ≥40% of longest; SPSS truncation), `_group_text`. `test_battery_group.py`: `suggest_batteries` `min_members`/`min_subjects` thresholds, `_cells` ≥3 split, `apply_batteries` qid slug-collision `-2/-3`, prepend order. `test_enrich_model.py`: the public orchestrator end-to-end on synthetic + a hand-built grid model (multi-first-then-battery ordering).

**stats** — `test_statistics.py`: `pct` (zero base→0, decimals), `count_value` (ceil vs round), `mean`/`summary_value` (drop missing+NaN, empty→0.0). `test_base_rules.py`: `single_base`, `multi_base` (respondents not selections), `segment_bases` (Total + per-code, integer labels, ordering). `test_aggregate.py`: total-only, with-classifier, non-integer code labels, NULL exclusion. `test_sorting.py`: each basis + descending + data_order + tie-stability + unknown-basis KeyError. `test_series.py`: `Cell.value` (core + `extra`), `SeriesResult.cell`/`n_series`/KeyError, `is_partition` (single-choice yes, multi-overlap no, multi-segment no, pct fallback). `test_engine_single.py`: column %, missing exclusion, `_rating_scale`+`is_rating` reorder (out-of-order codes 2,3,4,5,6,1,7→1..7), `show_not_answered` (bucket last, base=total, sum 100), `show_empty_categories=False` drop-displayed-zero (0% dropped, 0.4% kept), `not_answered_codes` None vs () vs value, label overrides. `test_engine_multi_summary.py`: `_multi` one-bar-per-member; `_summary` mean in `Cell.mean`, other stats in `extra`, with/without classifier. `test_engine_battery.py`: `_battery` mean-per-member, `_battery_stacked` (levels=cats, statements=segs, per-statement 100%), `_battery_comparison` parallel-battery entities×attributes. `test_engine_wordcloud_combo.py`: `_wordcloud` (stopwords/short/digits/non-answers dropped, deterministic top-N, no-words→ValueError, non-text→clean error), `_combo_two_var` + fallback-on-exception. `test_engine_helpers.py`: `_relabel_segments` derived-binary `{"1":label,"0":"Muut"}`, `_auto_pct_decimals` boundaries, `_effective_missing`.

**model** — `test_question_model.py`: frozen dataclasses, `question()`/`variable()` KeyError, `missing_value_labels`. `test_report_serde.py`: `report_to_json` canonical/deterministic, `report_from_json` (None-vs-()-vs-value for not_answered_codes, label_overrides dict OR pairs, nested defaults, scatter_xy tuple/None), round-trip equality.

**render (pure)** — `test_config_schema.py`: `ConfigField.to_dict` shape; each family (standard optional classifying, **stacked required** [documents current state — flips when Task #1 lands], single_series omits classifying, combo adds combo_secondary, note-only). `test_plugin_registry.py`: all 12 registered, `plugin()` KeyError lists known types, `register` idempotent, `suggest_chart_type` (score/tie/fallback, swallows exceptions). `test_suitability_matrix.py`: per-plugin `suitability`/`suggest` for all 12 (parametrized) — the gap the existing suite only covers for pie. `test_shape.py`: `SeriesShape.of` (n_series, is_multi, is_temporal via TIME_RE, is_partition, ADDITIVE_STATISTICS). `test_mpl_helpers.py`: `series_values`, `series_is_empty`, `wrap_label`/`wrap_label_capped`, `auto_decimals`, `format_value` — no figure needed.

**ai (pure)** — `test_text_prompts.py`: prompt builders include the study line/findings block (fake `chat` records the prompt). `test_text_parsing.py`: `_parse_numbered`, `_parse_bullets` (fences/markers/cap 6), `_postprocess_short` (MAX_LABEL_LEN 24, strip ellipsis, fallback), `shorten_labels` (reference-verbatim → 0 AI calls, EgoHiveError swallowed → {}, order preserved, only short≠full), `pick_demographic_questions` (drop hallucinations, dedup), `generate_data_chat` fence-scrub + empty→canned. `test_reference.py`: `_normalize`, `ReferenceLabels.match` (exact then fuzzy 0.9, only strictly-shorter), `examples`. `test_egohive_client.py`: monkeypatch `urllib.request.urlopen` — `_create_session` sends `X-Endpoint-Key` only when key present + `Origin`; `_send_message`; `egohive_chat` two-call flow + markdown/quote strip + newline preserve; error translation (HTTPError→`HTTP {code}`, URLError→"unreachable"); `load_creds` env-precedence; `_clean`/`_build_prompt`.

### INTEGRATION (composition, in-process)

**render** — `test_image_matrix.py`: parametrized over all image-capable types → `compute()`→ctx→`IMAGE_BUILDERS[type](ctx)` places exactly one PICTURE (PIL: valid PNG, no distortion, letterbox fit). `test_native_matrix.py`: native builders place a `c:chart` (or the funnel BAR_STACKED), `combo`/`wordcloud` native raise `NativeUnsupportedError`, `series_chart_data` shape. `test_deck_assembly.py`: `render_report` native vs image dispatch, completeness + native-purity asserts, `render_to_file` reopen, multi-chart, bullet/demographics special slides. `test_empty_degrade.py`: `series_is_empty`→`render_empty_chart`, compute-failure→`_empty_series` in `build_pptx`.

**export** *(`@pytest.mark.export`)* — `test_pptx_build.py` is soffice-free (build a deck, reopen, count shapes, both render modes). `test_export_soffice.py`: `pptx_to_pdf` + `pdf_page_count` + `rasterize_pages` + `run_fidelity_gate` native layer-2 (skip if soffice/poppler absent).

**api** — all via `create_app(client=Mock(spec=DataHiveClient))` or `InMemoryDataHiveClient`. `test_health_and_errors.py`: `/health`; the full `DataHiveError`→HTTP table (400/401/403/404/409/422 identity; 500/503/other→502; detail `"datahive: …"`≤500; is-a RuntimeError) — assert through **multiple** routes, not just reports GET. `test_cases_crud.py`: create/list/rename(422 empty, 404 missing, 501 when absent)/delete(cascade via memory client). `test_materials.py`: upload → `{material_id, question_count, file_label}`, read_sav invoked. `test_questions.py`: `/questions` fields, `/questions/{qid}/summary` (+404), `/variables` sort/filter, `/chart-types`, PUT `/grouping` (multi 422s, single, 500 branch). `test_reports_crud.py`: create/get/put(404-on-deleted, 422 invalid body)/delete/duplicate. `test_render_routes.py`: orchestrate wiring (mock build/convert), `view` passthrough, `ValueError`→422, `render_output_dir` sanitize, preview.pdf/.pptx 404-before-render. `test_preview_chart.py`: scatter-no-xy→422, stacked-no-classifying→422 *(current behavior; updated when Task #1 lands)*, cache single-render, soffice-absent→503, render-failure→422.

**store** — `test_memory_client.py`: in-memory + persistence (round-trip across restart, `_n` continuity, corrupt-tolerant load, atomic files, cascade delete, byte-exact material, `get_material` missing raises). `test_datahive_rest.py`: `httpx.MockTransport` for all 8 methods (create_case id/project_id, save/load verbatim, aggregate filters, attach multipart, get_material bytes, non-2xx→`DataHiveError`).

### AGENTIC

- `test_ai_routes_mocked.py` *(deterministic)*: every AI route with monkeypatched `egohive_chat` returning canned replies + patched `_reference_labels`. Assert: success shapes; 404 unknown q; 422 bad body (short-labels neither field, chat empty); **503 on `EgoHiveError`**; degrade paths (slide-title empty-findings→question.text no LLM; short-labels unreachable→200 originals; themes/conclusion no-data→[]; chat empty-reply→canned Finnish). Closes the existing gaps: **`/themes` and `/chat`**.
- `test_ai_text_orchestration.py`: the `reportbuilder.ai.text` functions with a recording fake `chat` — two-LLM demographics flow, findings→prompt, parse→response for each generator.
- `test_ai_live.py` *(`@pytest.mark.live`)*: real `egohive_chat` via slide-title + chat; self-skip on `EgoHiveError`. Reads env/`work/egohive_creds.json`.

### E2E

- `test_pipeline_image.py` *(soffice-free)*: `synthetic_sav` → `read_sav` → `enrich_model` → for a set of chart types, `compute` → image build → one PICTURE. Full data→render path, no LibreOffice.
- `test_pipeline_export.py` *(`@pytest.mark.export`)*: synthetic → `build_pptx` → `pptx_to_pdf` → `pdf_page_count`==#slides, both render modes; native-mode PDF text-layer fidelity via `numbers_from_pdf`.
- `test_api_full_chain_memory.py`: `InMemoryDataHiveClient` through the API — case→upload→questions→report create/get/duplicate→(render is export-gated). Uses the **real memory client** (the NSIGHT_DEMO seam) in-process without requiring `NSIGHT_DEMO=1`.
- `test_demo_real_savs.py` *(`@pytest.mark.demo`)*: the three client SAVs via the local-fs demo app — upload each, list questions, preview a representative chart per file (PNG assert export-gated), create+render a small report.

---

## Build Order (milestones)

Each milestone ends green and is committed. Build unit → integration → agentic → e2e (bottom-up: fast deterministic core first).

- [x] **M0 — Suite scaffold.** `tests/suite/` tree, `tests/suite/conftest.py` (shared fixtures), register `export` marker, a smoke test. Green.
- [x] **M1 — Unit: data layer.** ingest + stats + model (`unit/ingest`, `unit/stats`, `unit/model`). Highest count; closes engine/ingest gaps. Green.
- [x] **M2 — Unit: render + ai.** `unit/render` (config_schema, plugin registry, suitability matrix, shape, mpl helpers), `unit/ai` (prompts, parsing, reference, egohive_client urlopen-mock). Green.
- [x] **M3 — Integration: render + export + store.** image/native matrices, deck assembly, empty-degrade, pptx_build, export(soffice-gated), memory + datahive REST. Green (export-gated tests skip cleanly).
- [x] **M4 — Integration: API.** health/errors, cases, materials, questions, reports, render routes, preview-chart. Green.
- [x] **M5 — Agentic.** mocked routes + text orchestration (deterministic), live group (`@pytest.mark.live`). Green (live self-skips).
- [x] **M6 — E2E.** image pipeline, export pipeline (gated), API full chain via memory client, demo real-SAV group (`@pytest.mark.demo`). Green.
- [x] **M7 — Coverage sweep.** Run `pytest tests/suite --cov=reportbuilder --cov=nsight` (if pytest-cov present) or a completeness pass against this plan's matrices; log any deliberate gaps. Green.

## How to run

```bash
cd /home/johan/Projects/nsight/proto
# Standard deterministic suite (no soffice, no network):
.venv/bin/python -m pytest tests/suite -q
# Export group (needs LibreOffice + poppler):
.venv/bin/python -m pytest tests/suite -m export -q
# Agentic live group (needs local egoHive; self-skips otherwise):
.venv/bin/python -m pytest tests/suite -m live -q
# Demo real-SAV group (local-fs store; needs SAV copies):
NSIGHT_DEMO=1 .venv/bin/python -m pytest tests/suite -m demo -q
```

## Notes on the postponed defect (Task #1)

The stacked-bar "total-only" fix is **out of scope here** and queued. Two suite tests document the *current* (pre-fix) contract and are the ones to flip when it lands: `unit/render/test_config_schema.py` (stacked `classifying_var` required) and `integration/api/test_preview_chart.py` (stacked-no-classifying → 422). They are marked with a `# TODO(stacked-total-only)` comment so the fix is a one-line find.

---

## Completion status (2026-07-01)

All milestones M0–M7 complete. **892 tests** added under `tests/suite/`, all green; no product code changed.

| Layer | Tests | Notes |
|---|---:|---|
| unit/ingest | 135 | sav helpers, curation, multi_group, battery_group, enrich_model |
| unit/stats | 101 | statistics, base_rules, aggregate, sorting, series, all engine paths |
| unit/model | 77 | question model, report serde (tri-state not_answered_codes, label overrides) |
| unit/render | 247 | config_schema, plugin registry+suggest, 12-type suitability matrix, shape, _mpl |
| unit/ai | 74 | prompts, parsing, reference, egoHive client (urlopen-mocked) |
| integration/render | 53 | image+native builder matrices, deck assembly, empty-degrade |
| integration/export | 12 | build_pptx (free) + soffice/poppler-gated pdf/fidelity/preview |
| integration/store | 61 | InMemoryDataHiveClient + DataHiveClient REST (MockTransport) |
| integration/api | 72 | health/errors table, cases, materials, questions, reports, render, preview |
| agentic | 44 | all 8 AI routes mocked + text orchestration; 4 live-gated |
| e2e | 12 | image pipeline, export pipeline, API full-chain (memory), demo real-SAVs |
| **total** | **892** | 686 run in the standard suite; 206 gated (export/demo/live) |

**Run status:** standard `pytest tests/suite` → 886 passed, 6 skipped (4 live + 2 demo self-skip). `NSIGHT_DEMO=1 … -m demo` → 2 passed (the three real client SAVs). Full tree (`tests/rb` + `tests/suite`, not live/demo) → 1617 passed, no regressions.

### Product findings surfaced (documented in tests as actual behavior; NOT fixed — separate from Task #1)
1. `nsight.agent.egohive_client._request` wraps only `HTTPError`/`URLError`; a mid-stream `ConnectionResetError`/`OSError` (e.g. server reset) leaks unwrapped past `EgoHiveError`. The `test_ai_live.py` group compensates by catching `(EgoHiveError, OSError)`. Candidate hardening.
2. `reportbuilder.ai.text.generate_slide_title` does **not** enforce `MAX_TITLE_LEN` (it's prompt guidance only) — a long model reply passes through untruncated.
3. `generate_data_chat` returns `""` for an empty model reply; the Finnish "En osaa vastata…" fallback lives only in the `ai_chat` route, not the generator.
4. `_parse_bullets` preserves `**bold**` markers (only `_clean` strips emphasis), so themes/conclusion/demographics bullets can contain markdown.
5. `render_output_dir` is a deterministic shared `/tmp/nsight-render/<case>/<report>` dir; with the in-memory client's per-store id reset, prior renders can collide on reused ids — the render-route tests `rmtree` first. Worth an id-namespacing review.

These are logged for a future queue item; none block the suite.
