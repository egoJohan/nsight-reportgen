# nSight automated deck generation — status & architecture (for the proposal)

_Last updated: 2026-06-02_

## Bottom line

- **The hard, valuable core is built and independently verified:** turning raw SPSS
  survey data into the exact tabulated numbers behind the deck's charts. Proven by
  *reconstructing the original deck's numbers after deleting them* (construction proof).
- **The agent + LLM layer is egoHive, not a bespoke agent.** egoHive already provides
  agent orchestration with a **Gemini** provider (function-calling). nSight should be
  **tool plugins on egoHive** + **datahive** as the data plane. (An earlier bespoke
  Claude/Gemini narrator was a misstep and has been removed.)
- **Honest gaps are listed below** so the proposal can scope the remaining work accurately.

## What is actually built and verified (real, tested)

The deterministic data engine + rendering + fidelity harness (`/home/johan/Projects/nsight/proto`):

- Ingest `.sav` → DuckDB tabular store (datahive's `TabularStore`) + codebook.
- Tools: segments, weighted shares/cross-tabs, perception split, top-of-mind, spontaneous
  any-mention, open-ended word coding. **Every chart number is computed in Python — never
  by an LLM.**
- Renders into the native PowerPoint charts/tables/text of nSight's template (in place,
  preserving house styling), plus a fidelity harness that scores generated vs original.
- **64 automated tests** (54 unit + 10 integration golden tests against the real Attendo
  `.sav` + `.pptx`).

**Accuracy vs the real Attendo deck (golden tests):**

| Metric | Result |
|---|---|
| Aided awareness, 9 brands | **exact** (0 pp) |
| General opinion (positive/neutral/negative), private + public | **exact** ("Positiivinen 58 %") |
| Spontaneous awareness + top-of-mind, 12 brands | **±1 pp** |
| Brand-image TOP-10 word list | **10/10 lemmas** |

**Construction proof** (`scripts/construction_proof.py`): blank the engine-written data out
of the template (set those chart series to 0), then regenerate from the SPSS file:

- Aided awareness — reconstructed **exactly** (9/9).
- General opinion — reconstructed **exactly** (5 series × 2 columns).
- Spontaneous — reconstructed within **~1–2 pp**.

→ The engine **builds** the chart content from the data; it does not merely copy the
original deck. (Chart *styling* is the fixed nSight template, by design.)

**DataHive verified as the data plane** (against the live `testhive`):

- Ingest via `POST /api/v1/ingest/sav` → 229 vars / 1001 cases.
- `survey_codebook` MCP tool returns the aided-awareness `var18` grid + value labels.
- `recall` semantic search works.
- Respondent rows round-trip losslessly (Attendo = 863/1001 = **86.2 %**, matching the deck).
- (Found + fixed a real datahive ingest bug: crash on `.sav` files with a date column.)

## Corrected architecture (use what we already have)

```
            ┌──────────────────────────────────────────────┐
            │  egoHive  (agent-orchestration platform)      │
            │  • Agent: Gemini model + system prompt        │
            │           + enabled tools + KB (the brief)    │
            │  • Gemini LLM provider (function-calling)     │
            │  • auth / scheduling / chat / KB              │
            └───────────────┬──────────────────────────────┘
                            │ calls function-tools
            ┌───────────────▼──────────────────────────────┐
            │  nSight tool plugins (egoHive Tool contract)  │
            │  • nsight_tabulate(metric, segment, …)        │  ← deterministic numbers
            │  • nsight_generate_deck(brief) → .pptx        │
            └───────────────┬──────────────────────────────┘
                            │ reads survey data + codebook
            ┌───────────────▼──────────────────────────────┐
            │  datahive  (AI data plane)                    │
            │  • SPSS ingest, codebook (MCP survey_codebook)│
            │  • respondent rows (DuckDB tabular store)     │
            └──────────────────────────────────────────────┘
```

- **egoHive** owns the agent + the **Gemini** provider (it has a `gemini` LLM-provider
  plugin with function-calling, and tools are first-class plugins — `calculator`,
  `pdf_create`, `diagram`, etc. are precedents). An agent is configured with a model, a
  system prompt, enabled tools, and knowledge bases.
- **nSight** is delivered as egoHive **tool plugins** implementing egoHive's `Tool`
  contract (`tool_id`, `definition` = name + description + JSON-schema params, `async
  execute(parameters, context)`). The deterministic tabulation/render engine we built maps
  directly onto these.
- **datahive** stores the source material and serves the codebook (MCP) + respondent rows.
- The **natural-language brief** becomes the agent's system prompt / a KB document. Gemini
  orchestrates and writes the Finnish prose; **the numbers come only from the tools.**

## Verified runtime (this environment, 2026-06-02)

- **egoHive backend is LIVE** — `egohive-egohive-api-1` healthy at `127.0.0.1:8000`,
  API base `/api/v1/` (auth, agents, chat, sessions).
- **A real Gemini key is configured and `SIM_MODE=false`** — egoHive can produce genuine
  Gemini output right now (Gemini via the Google GenAI Developer/AI-Studio API, key held in
  KeyHive). So a live end-to-end run is possible the moment we have an egoHive auth token.
- **datahive is LIVE** (`datahive-testhive` :7902) and verified as the data plane.

## Product surfaces (both, phased)

- **Phase 1 — batch deck generator:** SPSS + brief → deck. Uses egoHive's **Gemini agent**
  only to write the Finnish prose; the deterministic engine does the rest. **No nSight tool
  plugins needed.** Integration = call the running egoHive agent/chat API for the prose.
- **Phase 2 — interactive analyst agent:** an analyst chats; the Gemini agent answers
  ad-hoc survey questions and regenerates decks on command. **This is the only surface that
  needs nSight packaged as egoHive tool plugins** (`nsight_tabulate`, `nsight_generate_deck`
  against egoHive's `Tool` contract). The same functions back both surfaces.

## LIVE end-to-end achieved (2026-06-02)

The full Phase-1 chain runs against live infrastructure with **real Gemini output**:

> deterministic numbers (from datahive-stored SPSS) → **egoHive Gemini agent** writes the
> Finnish key message → deck rendered.

- `uv run python scripts/generate_live.py` produces `work/attendo_generated.pptx` where the
  slide-14 key message is written by Gemini (via egoHive), e.g.
  *"Attendo johtaa autetussa tunnettuudessa selkeästi 86 %:lla."* (phrasing varies per run —
  it is genuinely live, not SIM).
- egoHive integration: `src/nsight/agent/egohive_client.py` (`egohive_narrate`) authenticates
  to the running egoHive (`custom_jwt` / `DEV_AUTH`), drives a Gemini agent ("nsight-demo",
  model `gemini-2.5-flash`) via its endpoint/session/chat API, returns the prose. Config in
  `work/egohive_creds.json` (gitignored).
- Numbers are still computed only by the deterministic tools; Gemini only phrases them.

Caveat: the egoHive agent/endpoint rows were bootstrapped partly via direct Postgres inserts
in the running dev container (the product-deploy happy-path needs the builder UI); they live
in that container and are documented in the creds file. Productionizing = create the agent
through egoHive's normal flow.

## Honest gaps / not done yet
- **nSight not yet packaged as egoHive tool plugins** — Phase 2 only (the interactive
  surface); the batch generator does not need them.
- **Coverage:** 4 metric/slide types are regenerated and verified; the other ~52 slides are
  carried through from the template unchanged. The **segment-split slide is not
  reproducible** from this `.sav` (its bases — experience 608 / no-experience 245 /
  recommenders 234 / professionals 257 — come from survey routing / a derived population
  not present in the file). Flagged, not faked.
- **Open-ended word _counts_ differ** from the deck (the deck used manual thematic merging
  beyond synonym mapping); the TOP-10 lemma _set_ matches 10/10.
- **datahive gap:** no MCP tool for tabular cross-tab aggregation — the tools read the
  DuckDB tabular store directly. A clean MCP-only integration would add a server-side
  aggregation tool.

## Path to the offering (scope for the proposal)

1. **Package the engine as egoHive tool plugins** (`nsight_tabulate`, `nsight_generate_deck`)
   against egoHive's `Tool` contract. _(small–medium)_
2. **Configure an egoHive agent**: Gemini model + nSight tools + the brief as system
   prompt/KB. _(config)_
3. **Add a server-side tabular-aggregation tool to datahive** for clean MCP-only data
   access. _(medium)_
4. **Expand brief coverage** slide-by-slide (mechanical per metric: bind variables, read
   deck ground truth, add a golden test).
5. **Generalize beyond Attendo** to the other study types (loyalty, segmentation) — each is
   its own brief + variable bindings + golden tests.

## Recommended proposal demo

> SPSS file → egoHive agent (Gemini) calls nSight tools → regenerated Attendo deck.
> Evidence: the **construction proof** (blank → rebuild from data) shows the numbers are
> computed; the **golden-test table** (computed == deck) is the accuracy claim.

Artifacts that exist today:
- `work/attendo_generated.pptx` — full styled deck with 4 metric types regenerated from data.
- `work/attendo_blanked.pptx` + `work/attendo_from_blanked.pptx` — the construction proof.
- `uv run python scripts/construction_proof.py` — reproduces the proof.
- `uv run pytest -m integration -s` — the accuracy golden tests against the real files.
