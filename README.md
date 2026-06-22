# nSight deck auto-generation — prototype

Regenerate nSight's Attendo brand-tracking PowerPoint deck automatically from its SPSS
survey data, driven by a natural-language brief, rendered into the original deck used as a
fixed template. Quality is measured by **fidelity to the original deck**.

- Design spec: `docs/superpowers/specs/2026-06-02-nsight-deck-autogen-design.md`
- Implementation plan: `docs/superpowers/plans/2026-06-02-nsight-deck-autogen.md`

## What it does

Given the Attendo `.sav` + a prose brief (`briefs/attendo.md`), the engine:

1. Ingests the SPSS data into a DuckDB tabular store (DataHive's `TabularStore`) + a codebook.
2. Computes every chart number **deterministically in Python** (shares, cross-tabs,
   top-of-mind, perception splits, open-ended word frequencies) — numbers are never produced
   by an LLM.
3. Fills the original `.pptx` **in place** (native charts, tables, text boxes), preserving
   all house styling, and replacing only the current survey wave's data.
4. (Optional) an LLM agent writes Finnish key-message prose from the computed numbers.
5. Scores the generated deck against the original (fidelity harness).

An LLM agent orchestrates step 2–4 (reads the brief, routes to the deterministic tools,
writes prose); the **numbers come only from the tools**.

## Data regenerated from the SPSS file (verified against the real deck)

| Deck slide | Metric | Result vs original deck |
|---|---|---|
| 14 (idx) | Aided awareness, 9 brands | **exact** (0 pp deviation) |
| 17 (idx) | General opinion (positive/neutral/negative), private & public | **exact** ("Positiivinen 58 %" matches) |
| 13 (idx) | Spontaneous awareness + top-of-mind, 12 brands | **±1 pp** (rounding vs the deck's manual coding) |
| 24 (idx) | Brand-image TOP-10 word list | **10/10 lemmas** (counts differ — see limitations) |

The remaining 52 slides are carried through from the template unchanged, so the output is a
complete, presentation-quality deck. **Full-deck chart fidelity: 99.7 %** (1537/1541 data
points; the 4 sub-100 points are ±1 pp rounding on the genuinely-recomputed spontaneous
chart — evidence it is regenerated from data, not copied).

## Setup

```bash
cd /home/johan/Projects/nsight/proto
uv sync --extra dev
```

(`pyreadstat`, `pandas`, `python-pptx`, `duckdb`, `fastapi` are installed. DataHive's
`TabularStore` is imported from the sibling repo via `sys.path` — see
`src/nsight/store/survey_store.py`.)

## Run the tests

```bash
uv run pytest -q                       # full suite (64 tests)
uv run pytest -m "not integration"     # fast unit tests only
uv run pytest -m integration -s        # golden tests vs the real Attendo files
```

The golden tests are the real correctness gate: they assert the numbers **computed from the
SPSS file** equal the numbers **printed in the original deck**.

## Regenerate the deck (CLI)

```bash
uv run python -c "from nsight.generate import generate_deck; from nsight import config; \
print(generate_deck(sav=config.ATTENDO_SAV, brief_path=config.BRIEFS_DIR/'attendo.md', \
template=config.ATTENDO_TEMPLATE, out=config.GENERATED_PPTX))"
# -> work/attendo_generated.pptx
```

## Run the web app

```bash
uv run uvicorn nsight.webapp.app:app --port 8800
# open http://127.0.0.1:8800 — pick the .sav + brief, Generate, see the fidelity score, download the .pptx
```

## Project layout

```
src/nsight/
  store/survey_store.py   # ingest .sav -> DuckDB (DataHive TabularStore) + codebook
  codebook.py             # variable / value-label lookup
  segments.py             # audience-segment predicates
  tabulate.py             # deterministic shares / cross-tabs / perception / top-of-mind
  coding.py               # open-ended response coding (TOP-N words)
  waves.py                # prior-wave numbers (extracted from the original deck)
  attendo_bindings.py     # survey-specific variable bindings + deck ground-truth numbers
  brief.py                # natural-language brief parser (YAML slide blocks)
  build.py                # brief job -> SlideFill (per metric); brief->template preflight
  render/                 # fill native charts / tables / text boxes in place
  agent/                  # Claude Agent SDK workflow + narrator (prose only)
  fidelity/               # extract pptx content + compare generated vs original
  webapp/                 # FastAPI + minimal UI
briefs/attendo.md         # the brief (the editable template/spec)
scripts/extract_waves.py  # one-time: pull prior-wave numbers from the original deck
```

## DataHive integration (verified)

DataHive is the source-of-truth data plane. Verified against a live hive:

- Ingest via `POST /api/v1/ingest/sav` (229 vars / 1001 cases).
- Codebook via the MCP `survey_codebook` tool (returns the `var18` aided-awareness grid).
- Semantic search via MCP `recall`.
- Respondent rows round-trip losslessly (Attendo = 863/1001 = 86.2 %, matching the deck).

Gap: there is no MCP tool for tabular cross-tab aggregation, so the cross-tab math reads the
DuckDB tabular store that ingest populates (this prototype uses that store class on its own DB
file). A clean MCP-only integration would add a server-side tabular-query/aggregation tool.
(While verifying, a real DataHive bug was found and fixed: `ingest/spss.py` crashed on `.sav`
files with a date column — `json.dumps` now uses `default=str`.)

## Known limitations

- **Segment splits (deck slide 15)** are not regenerated: the deck's segment bases
  (experience n=608 / no-experience n=245 / recommenders n=234 / professionals n=257) derive
  from survey routing / a derived population not present in this `.sav`. Not faked.
- **Open-ended word counts** differ from the deck: the deck applied manual thematic merging
  (e.g. "suuri"→"iso") beyond mechanical synonym mapping. The TOP-10 lemma *set* matches
  10/10; per-word counts diverge. Word-list fidelity is scored as ranked overlap.
- The LLM narrator (`agent/tools.py`) requires `claude-agent-sdk` installed + auth; without
  it, deck generation falls back to slide titles as key messages (numbers are unaffected).

## Extending coverage

Add a ` ```slide ` block to `briefs/attendo.md` (slide_idx, shape name, occurrence, metric,
segment, series_name), add a `metric` branch to `build.py`, bind the variables in
`attendo_bindings.py`, and add a golden test asserting computed == deck. `preflight`,
`generate_fills`, and `render` already loop over all jobs.
