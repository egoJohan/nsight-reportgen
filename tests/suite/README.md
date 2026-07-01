# nSight backend test suite (`tests/suite/`)

A fresh, ultra-extensive, **deterministic-by-default** test suite covering the whole
nSight backend (`src/reportbuilder` + the `src/nsight` egoHive client) across four
layers. It lives alongside — and does not replace — the older `tests/rb` tree.

> Full strategy, per-layer matrices, and completion status:
> `docs/superpowers/plans/2026-07-01-backend-test-suite-plan.md`.

## Layout

```
tests/suite/
  conftest.py        # shared fixtures (DataHive seams, synthetic model, canned chat, soffice gate)
  _helpers.py        # non-fixture helpers: make_ctx, assert_single_picture, RecordingChat
  unit/              # pure functions — ingest, stats, model, render, ai
  integration/       # composition — render, export, store, api
  agentic/           # AI routes + text orchestration (mocked) + live-gated
  e2e/               # full pipeline (synthetic), API full chain, real-SAV demo
```

Every directory is a Python package (`__init__.py`), so modules are namespaced
`suite.*` and never collide with `tests/rb`. Import shared helpers with
`from suite._helpers import ...`.

## Running

Interpreter: `.venv/bin/python`. Run from the repo root.

```bash
# Standard suite — deterministic: no network, no LibreOffice. This is the gate.
.venv/bin/python -m pytest tests/suite -q

# One layer / one file / one test
.venv/bin/python -m pytest tests/suite/unit/stats -q
.venv/bin/python -m pytest tests/suite/integration/api/test_cases_crud.py -q
```

### Gated groups (opt-in via markers)

| Marker | Needs | Command | Behaviour when unavailable |
|--------|-------|---------|----------------------------|
| `export` | LibreOffice (`soffice`) + poppler | `.venv/bin/python -m pytest tests/suite -m export -q` | skips |
| `demo` | `NSIGHT_DEMO=1` + the three client SAVs | `NSIGHT_DEMO=1 .venv/bin/python -m pytest tests/suite -m demo -q` | skips |
| `live` | a locally-running egoHive | `.venv/bin/python -m pytest tests/suite -m live -q` | self-skips on `EgoHiveError` |

The standard `pytest tests/suite` run **includes** `export` tests when the tools are
present and **skips** `demo`/`live` (they never run without their opt-in). Everything
runs **locally** — never against staging.

Real client SAVs for the `demo` group are read only from the gitignored
`tests/rb/e2e/data/sav/` (fallback: tracked `input/`); populate them per
`tests/rb/e2e/data/README.md`. They are IPR and must never be committed.

## Conventions

- **Deterministic by default.** No wall-clock/random dependence; matplotlib runs Agg (headless).
- **Seams:** DataHive is injected via `create_app(client=Mock(spec=DataHiveClient) | InMemoryDataHiveClient)`; the LLM boundary is mocked by monkeypatching `reportbuilder.api.routes_ai.egohive_chat` or passing a fake `chat=`; the egoHive client's only network call (`urllib.request.urlopen`) is mocked for client-internals tests.
- **The product is the source of truth.** Tests assert *actual* behaviour discovered by running the code — they never drive a change to `src/`.

## Fixing a defect: manifest-first, then fix, then re-test (loop until fixed)

When a bug is reported, do **not** patch first. Follow the red→green loop so the
suite proves both the bug and the fix:

1. **Manifest (RED).** Add or adjust a test that expresses the *desired* behaviour
   and encodes the reported failure. Put it in the layer that owns the bug (a unit
   test if a pure function is wrong; an integration/api or e2e test if it only
   appears through composition). Give it clear inputs and the expected correct output.
2. **Confirm it FAILS** against unmodified `src/`:
   ```bash
   .venv/bin/python -m pytest tests/suite/<path>::<test> -v   # must be RED first
   ```
   If it passes before any change, it isn't reproducing the bug — fix the test, not the product.
3. **Fix** the minimal production code.
4. **Re-test (GREEN):** re-run that test, then the surrounding file/layer, then the
   whole suite to catch regressions:
   ```bash
   .venv/bin/python -m pytest tests/suite/<path>::<test> -v
   .venv/bin/python -m pytest tests/suite -q
   ```
5. **Loop** steps 3–4 until the manifest test — and the full suite — are green. If the
   fix reveals further cases, add a manifest test for each (back to step 1).

No production edit lands before its RED test exists. Tests that document a *current*
contract awaiting a queued fix are tagged `# TODO(<slug>)` so the flip is a one-line
find — e.g. the queued stacked-bar total-only fix
(`docs/superpowers/plans/2026-07-01-stacked-bar-total-only-verification.md`) is
tagged `# TODO(stacked-total-only)` in `unit/render/test_config_schema.py` and
`integration/api/test_preview_chart.py`.
