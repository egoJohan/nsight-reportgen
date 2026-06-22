# nSight deck auto-generation — prototype design

**Date:** 2026-06-02
**Status:** Draft for review
**Owner:** johan@egoiq.com

## 1. Summary

nSight produces market-research decks (brand tracking, loyalty, segmentation) as
PowerPoint presentations, built from SPSS survey data. The differentiating, error-prone
core of that work is turning respondent-level SPSS data into the exact tabulated numbers
behind each chart.

This prototype builds an **agentic workflow plus a web app** that regenerates one such
deck automatically. The target is the **Attendo brand-tracking deck (Nov 2025)**:
given its SPSS file and a natural-language brief, the system produces a `.pptx` deck
rendered into nSight's house style.

**Success metric:** fidelity to the original deck — primarily whether the chart numbers
match, plus structural and text correspondence. The original Attendo deck is the
ground truth; the prototype simulates its creation.

## 2. Scope

**In scope (prototype):**

- One study type: Attendo brand tracking.
- Full end-to-end generation: data → tabulations → charts → narrative text → assembled deck.
- A web app to run the workflow and inspect results.
- A fidelity evaluation harness comparing generated vs. original deck.

**Out of scope (prototype):**

- Loyalty (Holiday Club) and segmentation (Synsam) studies. The architecture should not
  preclude them, but they are not built or validated here.
- Generalizing the visual style beyond a fixed template (the prototype clones the original
  deck's theme/layouts).
- Production hardening, multi-tenant concerns, auth beyond what DataHive already provides.

## 3. Success criteria

1. Running the workflow on the Attendo Nov 2025 `.sav` + brief produces a `.pptx` deck.
2. The fidelity harness reports numeric agreement with the original deck across all data
   carriers — charts, data tables, and open-ended word lists; the primary goal is that
   tabulated values match the originals (within rounding).
3. The deck is rendered in nSight house style (cloned from the original), with charts as
   native, editable PowerPoint charts (not images).
4. The web app lets a user select the SPSS file + brief, run the workflow with live
   progress, download the deck, and view the fidelity comparison.

## 4. Key decisions (resolved during brainstorming)

| Decision | Choice |
|---|---|
| MVP boundary | Full end-to-end deck (built outward from the data→chart core) |
| Target study | Attendo brand tracking |
| Deck structure source | Fixed blueprint expressed as a **natural-language brief**; agents fill it |
| Trend / prior waves | Current wave from SPSS; historical waves extracted from the original deck and stored in DataHive; reproduce the original deck's trend callouts |
| Visual style | **Fixed template** cloned from the original Attendo `.pptx` |
| App form | **Web app** |
| Agent vs. code | **Agent orchestrates, deterministic code computes** — numbers are never LLM-generated |

## 5. Architecture

### 5.0 Deck anatomy (verified 2026-06-02)

Measured directly from `Attendo Bränditutkimus Marraskuu 2025.pptx`:

- **SPSS source:** 229 variables, 1001 cases — n=1001 matches the deck's "(n=1001)"
  annotations. Includes 31 string variables, among them the open-ended verbatims needed for
  slides 25–29.
- **56 slides.**
- **45 native, editable charts: 43 bar + 2 radar** (no pie/line/etc.). Charts are backed by
  embedded Excel data tables — not images.
- **13 slides contain data tables** (`<a:tbl>`): slides 14, 21, 23, 32, 34, 35, 39, 41, 43,
  45, 47, 49, 51. Cells carry both values and trend deltas as text (e.g. "-1 %", "+2 %").
- **Slides 25–29 are free-text word-frequency lists** (no chart, no table): TOP-10
  open-ended brand descriptors with counts, shown per wave (Touko 24 / Marras 24 / …).
- **Recurring segments** seen in titles: kaikki vastaajat, kokemusta omaavat, kokemattomat,
  ammattilaiset, suosittelijat.

These facts drive three engine capabilities (categorical tabulation, open-ended coding) and
three render fill modes (charts, tables, text boxes). They are the contract the prototype
must satisfy.

> Environment note: `python-pptx` and `pyreadstat` are **not installed** in either the
> proto or DataHive venv; both are prototype dependencies to add. SPSS parsing for ingest is
> handled inside DataHive (which already depends on pyreadstat).

### 5.1 Inputs & artifacts

- **SPSS data** — `input/spss AttendoSuomi-Brandiseuranta_112025.sav`, ingested into DataHive.
- **The brief** — a prose document describing the deck section by section. For each
  section/slide: which survey question(s), the visualization type (chart / data table /
  open-ended word list), segment cuts (e.g. all respondents / experienced / inexperienced /
  professionals / recommenders), the trend rule (which prior waves to compare), and the
  intended key message. The brief *is* the template/spec and is
  what an analyst maintains per study type. For the prototype it is aligned with the
  original deck's structure.
- **Fixed visual template** — the original Attendo `.pptx`, used as a styled skeleton:
  theme, slide layouts, native chart styles and positions, slide order. The engine fills
  content into this skeleton in place.
- **Historical waves** — prior-wave numbers (touko 25 / marras 24 / touko 24) extracted
  once from the original deck's charts/text and stored in DataHive as wave-history items,
  so trend comparisons can be reproduced.

### 5.2 DataHive as the data plane

DataHive (`~/Projects/egoiq/egohive/egohive-datahive`) already provides the storage and
retrieval substrate:

- **SPSS ingest** writes respondent-level rows into a DuckDB tabular store **and** stores
  the codebook (variable names, labels, value labels). Confirmed in
  `datahive/ingest/spss.py` (`tabular.insert_rows`, `insert_spss_variable_meta`).
- **`survey_codebook`** MCP tool exposes the codebook.
- **`recall` / `remember` / notes / triples** store and retrieve source material, the
  brief, and historical waves.

DataHive is the source of truth for: respondent data, codebook, the brief, and wave
history.

**Important constraint confirmed in the code (`datahive/storage/tabular.py`):**
`TabularStore.query` performs `SELECT * ... WHERE <filters> LIMIT n` only — it has **no
aggregation, GROUP BY, or COUNT**. It returns filtered respondent rows, defaults to
`LIMIT 100`, and requires ABAC scope parameters (`scope_groups` / `scope_ceiling`). The
rows are stored **plaintext** in DuckDB (no at-rest envelope on the tabular store), so
they are directly usable once ABAC passes.

Consequences for the engine:

- Cross-tabs / shares / weighting are **computed in-process (Python, e.g. pandas/polars)**
  from respondent rows fetched via `TabularStore.query` — *not* via SQL aggregation in the
  store.
- The engine must pass a `limit` covering the full case count (n ≈ 1001+) and supply ABAC
  scope so it receives every respondent row, then aggregate.
- There is **no MCP tool** for tabular querying (MCP exposes only cite / expand / inventory
  / note / survey_codebook). Therefore the tabulation tools run **in-process as Claude
  Agent SDK local tools that call `TabularStore` directly**, not through DataHive's MCP.
  DataHive MCP is still used for `survey_codebook` and `recall`/`remember` of the brief and
  wave history.

### 5.3 Deterministic engine (the data-and-graphs core)

The highest-value, highest-risk component. All numbers come from here, never from the LLM.
Aggregation runs **in-process in Python** over respondent rows fetched from DataHive (see
§5.2), decoded against the codebook.

- **Segment dictionary** — many slides repeat across audience segments (kaikki vastaajat /
  kokemusta omaavat / kokemattomat / ammattilaiset / suosittelijat). Each segment is a
  deterministic predicate over respondent variables, defined once in a segment dictionary
  so every tool and every slide derives segments identically. Getting these predicates
  exactly right is a prerequisite for matching the deck's n= values.
- **Weighting** — weighted vs. unweighted shifts every percentage, so it is a primary
  fidelity lever. Note: a metadata scan of the `.sav` found **no weight variable under any
  obvious name** (no `weight`/`paino` in variable names or labels), so this tracker is
  plausibly reported **unweighted** — but a cryptically-named weight variable can't be ruled
  out. Resolution is empirical: reproduce one known chart (e.g. aided awareness) both
  weighted and unweighted and see which matches the original; lock that policy in and let
  the harness flag any chart that disagrees.
- **Categorical tabulation tools** — deterministic functions returning structured results:
  - frequency / share of a categorical variable (e.g. aided awareness % per provider),
  - cross-tab of a variable by a segment,
  - top-of-mind / spontaneous awareness aggregation (first-mention vs. any-mention),
  - perception splits (positive / neutral / negative), incl. the radar-chart profiles,
  - wave delta vs. stored historical waves (the "-1 %", "+2 %" deltas printed in tables).
  - All apply the agreed weighting policy (see Weighting above), missing-value handling
    (SPSS `user_missing` codes preserved raw on ingest; codebook decodes), and the deck's
    rounding convention (whole-percent).
- **Open-ended response coding tool** — slides 25–29 are spontaneous brand-image word
  lists ("Kallis (188), Kiireinen (68), …", TOP-10 with counts, shown across waves). These
  come from free-text variables, not categorical ones: the tool normalizes/codes the
  open-ended Finnish responses, counts term frequencies per segment, and returns ranked
  TOP-N lists with counts. Historical wave codings are stored alongside the numeric wave
  history so the side-by-side TOP-10-per-wave layout can be reproduced. This is a distinct
  capability from categorical tabulation and a notable accuracy risk (Finnish lemmatization
  / synonym collapsing must match how the original was coded). Source data is confirmed
  present: the `.sav` holds the open-ended responses as string variables (e.g. the seven
  spontaneous-awareness mentions `var17O35`–`var17O41`, plus brand-image word fields).
- **Render tool** — opens the fixed template and fills content **in place**, leaving all
  theme/layout/styling untouched. It has **three fill modes**, because the deck carries
  data in three ways (verified, §5.0):
  1. **Native charts** (43 bar + 2 radar) — replace data via `python-pptx`
     `chart.replace_data`, preserving chart type, styling, colors, and position. Keep
     series/category counts equal to the template's to retain per-point formatting.
  2. **Data tables** (13 slides) — fill table cells, including computed values *and* trend
     deltas rendered as cell text (e.g. "-1 %").
  3. **Text boxes** — titles, key messages, n= annotations, and the open-ended word lists,
     written as text runs with Finnish number/locale formatting matching the original.

### 5.4 Agentic orchestration (Claude Agent SDK)

A Claude Agent SDK (Python) workflow:

1. Reads the brief and plans the deck (ordered list of slide jobs).
2. For each slide job: calls the relevant tabulation / coding tool(s) with the right
   variable(s) and segment(s); receives exact numbers.
3. Composes the Finnish insight / summary / key-message text from those numbers.
4. Calls the render tool to fill the corresponding template slide.

**Brief → template binding.** Because the brief drives content while the template is a
fixed skeleton, each brief item must map to a specific template slide and to the specific
fill targets on it (which chart, which table, which text boxes). This binding is explicit,
not inferred at render time: each brief item carries a slide anchor, and the render tool
addresses targets by stable identifiers (e.g. shape names / indices captured once from the
template). A pre-flight check verifies every brief item resolves to a real template target
and every data-bearing template target is claimed by some brief item — so neither silently
drifts.

The agent decides *what* to compute and *how to phrase* findings; deterministic code
produces the numbers and the rendered slides. The agent has access to `survey_codebook`
(to map brief language to variable names) and the tabulation, coding, and render tools.

### 5.5 Web app

- **Backend:** FastAPI. Endpoints to: list inputs, trigger a generation run, stream
  progress/log, download the resulting `.pptx`, and return the fidelity report.
- **Frontend:** light UI to select the SPSS file + brief, start a run, watch live
  progress, download the deck, and view the fidelity comparison vs. the original.

### 5.6 Fidelity evaluation harness

Compares generated vs. original deck and produces a score the app surfaces. It must cover
all three data carriers (§5.0), not charts alone:

- **Per-chart numeric diff** (primary score) — extract native chart data from both decks
  and compare values per category/series. Tolerance must match the deck's rounding
  (whole-percent), so exact-after-rounding is the bar, not float equality.
- **Table-cell diff** — compare values and trend deltas in the 13 data tables.
- **Word-list diff** — compare the open-ended TOP-N terms and their counts (slides 25–29),
  scored as ranked-list overlap since coding may differ slightly.
- **Structure match** — slide count/order, chart/table/text-box presence per slide.
- **Text correspondence** — presence of expected titles / key messages / n= annotations.

The harness drives iteration: build a slice, score it, improve, repeat. It doubles as a
regression gate on the tabulation tools.

## 6. Components & responsibilities

| Component | Responsibility | Depends on |
|---|---|---|
| DataHive ingest | SPSS → DuckDB rows + codebook; store brief + wave history | DataHive (existing) |
| Segment dictionary | Deterministic predicates for each audience segment | codebook |
| Tabulation tools | In-process shares / cross-tabs / deltas (weighted) from respondent rows | `TabularStore.query`, codebook, segment dictionary |
| Open-ended coding tool | Code free-text responses → ranked TOP-N word lists with counts | respondent rows (free-text vars), codebook |
| Render tool | Fill fixed template in place: charts, table cells, text boxes | `python-pptx`, original `.pptx` template, brief→template binding |
| Agent workflow | Read brief, plan deck, call tools, write narrative | Claude Agent SDK, tabulation + coding + render tools, `survey_codebook` |
| Web app (API + UI) | Run workflow, stream progress, deliver deck + report | Agent workflow, fidelity harness |
| Fidelity harness | Score generated deck vs. original (charts + tables + word lists) | Both `.pptx` files |
| Wave-history extractor | One-time: pull prior-wave numbers + codings from original deck into DataHive | original `.pptx`, DataHive |

## 7. Data flow

```
SPSS .sav ──ingest──> DataHive (plaintext DuckDB rows + codebook)
                               │
brief (prose) ─────────────────┼──> Agent (Claude Agent SDK)
historical waves + codings ────┘        │
                                        │ per slide job (bound to a template slide):
                                        ├─> tabulation/coding tool
                                        │      └─ fetch respondent rows (TabularStore.query, ABAC, full n)
                                        │      └─ aggregate in-process (weighted) ──> exact numbers / word lists
                                        ├─> compose Finnish narrative from numbers
                                        └─> render tool ──> fill template in place (chart | table | text box)
                                                              │
                                                       generated .pptx
                                                              │
original .pptx ───────────────> fidelity harness <───────────┘
                                 (charts + tables + word lists)
                                        │
                                   fidelity report ──> web app
```

## 8. Build order

1. **Data→chart core.** Ingest the Attendo `.sav` into DataHive; define the segment
   dictionary and confirm n= against the deck; implement the first weighted tabulation tool
   (e.g. aided awareness % per provider) and the chart-fill render mode; fill a handful of
   real chart slides; stand up the fidelity harness and score those slides.
2. **Tables + wave history.** Add the table-fill render mode; extract prior-wave numbers
   from the original deck into DataHive; implement the wave-delta tool; reproduce the trend
   tables and callouts.
3. **Open-ended coding.** Add the free-text coding tool and text-box fill mode; reproduce
   slides 25–29 (TOP-N word lists per wave), storing historical codings.
4. **Full deck via the brief.** Write the Attendo brief covering all sections with explicit
   slide bindings; expand the tool set to cover every chart/table/word-list in the deck;
   fill the full template; pass the pre-flight binding check.
5. **Agent orchestration.** Wrap the pipeline in the Claude Agent SDK workflow (brief →
   plan → per-slide tool calls + narrative → render).
6. **Web app.** FastAPI + light frontend wrapping the workflow, with live progress,
   download, and the fidelity report.

## 9. Risks & mitigations

- **Weighting (highest-leverage).** If shares are reported on design weights and the engine
  computes unweighted (or vice versa), every percentage is off. No obvious weight variable
  was found in the `.sav`, so unweighted is the leading hypothesis — but unconfirmed.
  Mitigation: resolve empirically against one known chart before building out, then let the
  harness flag any chart that disagrees with the chosen policy.
- **Segment definitions.** Mis-derived segment predicates throw off both numbers and n=.
  Mitigation: the segment dictionary is built first and validated against the deck's printed
  n= values before any chart work.
- **Open-ended coding mismatch.** Finnish lemmatization / synonym collapsing may not match
  how nSight originally coded the free-text responses, so TOP-N lists may diverge.
  Mitigation: score word lists as ranked overlap (not exact), and capture the original
  coding scheme from the deck where possible.
- **Other tabulation correctness (missing values, rounding, first- vs. any-mention).**
  Mitigation: deterministic tools, harness as a regression gate, slide-by-slide validation
  against printed numbers, rounding matched to whole-percent.
- **Mapping brief language → SPSS variables.** The brief is prose; variable names are
  cryptic. Mitigation: the agent uses `survey_codebook` to resolve; the brief names the
  question/variable per section explicitly.
- **Render fidelity across three fill modes.** `chart.replace_data` must preserve styling
  (keep series/category counts equal); table-cell and text-box fills must not disturb
  layout. Mitigation: clone the original deck as the template, fill in place, address
  targets by stable identifiers, cover one carrier type at a time.
- **Trend reproduction depends on extraction quality.** Historical numbers and codings are
  read from the original deck. Mitigation: store them explicitly and verify against the deck.

## 10. Open questions for planning

- ~~Whether this tracker is weighted at all~~ **RESOLVED (2026-06-02): UNWEIGHTED.** No
  weight variable exists in the 229-variable file. Aided-awareness computed unweighted
  matches the deck exactly (0 pp deviation across all 9 categories). Aided awareness =
  the `var18O45..O53` grid, "knows" code `1.0` (Checked); brand→variable mapping is
  label-based, not column-ordered. Spontaneous awareness is a separate `var17O35..O44`
  open-list question. Deck current-wave series is labelled "Marraskuu 2025"; charts also
  carry prior waves (Toukokuu 2025 / Marraskuu 2024 / Toukokuu 2024) for trend reuse (M4).
- The exact derivation rule for each segment (kokemusta omaavat / kokemattomat /
  ammattilaiset / suosittelijat) from survey variables — confirm against the deck's n=.
  Target bases from the deck (slide 16, current wave): experience n=608, no-experience
  n=245, recommenders n=234, professionals n=257. Predicates still to be bound to variables.
- How nSight coded the open-ended brand-image responses. **PARTIALLY RESOLVED
  (2026-06-02):** image words = `var37O67/68/69` (3 word slots). With ~8 inflectional/
  spelling synonyms the engine reaches 10/10 TOP-10 overlap with the deck. BUT the deck also
  applied some *manual thematic* merges (e.g. "suuri"→"iso") that a synonym dict can't fully
  replicate, so individual word *counts* differ from the deck even where the ranked set
  matches. Word-list fidelity is therefore scored as ranked overlap, not exact counts.
- Frontend stack for the web app (minimal custom vs. reusing any existing UI scaffold).
