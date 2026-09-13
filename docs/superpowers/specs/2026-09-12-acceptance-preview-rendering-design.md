# Acceptance test for preview rendering — design

**Status:** draft 6, 2026-09-12. Author: Johan + Claude.
Draft 6 folds in six independent reviews (renderer internals; test engineering;
feasibility and performance; adversarial review of the merged draft 3) plus
facts measured directly against the tree. Every file and line citation has been
checked; performance figures are measured, and the probes behind them are in
`work/ops/claude_{draw_profile,cprofile,stage_timing,mem_growth,oracle_cost,artist_census}.py`.

## Why

Every chart defect this week reached us from a customer looking at a slide:
names printed through each other, a battery's rows cut to "Olen luottavainen,
että saan…" three times over, "4 %2 %" where two numbers shared a spot, a
picture already fixed but drawn by an editor tab from before the deploy. Each
was fixed with its own regression test, and each test guards the one slide it
was written for.

Nothing looks at the whole surface. A chart type nobody uses on staging — combo,
scatter, funnel and doughnut have **zero** slides there — can break for a year
unnoticed. A template with a narrow chart box, a dark ground or a wide font
changes every measurement the renderer makes, and no test draws on one.

This suite is that missing surface: **every study × every template × every chart
type and setup**, judged automatically, as the last gate before a deploy. Its
first duty is the defect the customer keeps reporting: **find any text printed
over any other text**, anywhere on any slide.

## Two facts the harness must get right, or nothing below holds

**1. Every request sends `render_title=False`.** `ChartSpecBody.render_title`
defaults to **`True`** (`api/routes_questions.py:1535`), and the composited fast
path is gated `if not body.render_title` (`:1975`). A harness built from §Scope
without this takes LibreOffice on every case — 10–20× slower, a different
rasteriser, and the eight-hour run this suite exists to prevent. Every timing in
this document assumes it. The flag selects only *how* a slide is rasterised,
never what is on it: the title is baked on both paths, gated instead on
`elements.title` (`_chart_spec_from_body`, `:1577-1586`). Note that
`title_box_headers`' docstring (`render/image/fast_preview.py:230-232`) reads as
if the fast path's slide carries no title; it means the compositor draws none of
its own, and is easy to misread.

**2. The rasteriser used must be reported by the product.** Today it is not
observable. `X-Title-Box` is present only on the fast path, but its **absence
does not mean fallback**: `fast_headers` is computed before the fast path runs,
gated on `not body.render_title and template_path` (`:1906-1907`), and
`title_box_headers` returns `{}` when the template's profile has no *positioned*
title or slide dimensions are 0 (`fast_preview.py:255-260`). The corpus
deliberately includes templates whose title is not positioned; those render
correctly on the fast path and carry no header. Asserting on it would redden
correct renders, and loosening it would stop detecting fallback.

**So `X-Preview-Path: composited | libreoffice` is a prerequisite**, not a
nicety — a one-line response header. Oracle 6's headline assertion and the whole
time budget depend on it.

## What it is

An **acceptance test** — a new, separate thing. It does not replace or modify the
existing suites (`tests/suite`, `tests/rb`), and no existing test is touched
unless this work genuinely breaks it.

| Mode | Purpose | Judged by | Runs |
|---|---|---|---|
| **Matrix** | Regression gate: everything we know, drawn every time | rules + baselines | full: ≤20 min, the deploy gate |
| **Quick** | "Is anything obviously broken" | rules + baselines | a few minutes |
| **Touched** | "I just changed the bar code" | rules + baselines | seconds to a minute |
| **Sweeps** | Thresholds: where a rule starts failing as one thing grows | rules only | part of the full gate |
| **Hunt** | Discovery: combinations nobody listed | rules only | on demand |

- **Quick** selects by coverage: every (chart type × template feature) pair, every
  setup dimension, every study, and every case a hunt promoted — by a fixed rule
  over the matrix index, so it grows automatically.
- **Touched** selects by code: the index records which builder drew each case, so
  a change under `render/image/bars.py` runs the bar cases. **The mapping is
  many-to-one** — 12 registry plugins are drawn by **8** modules: `bars.py` draws
  all four bar types and `pie.py` both pie and doughnut (`build_image_doughnut`,
  `pie.py:459`), the other six drawing one each. A `pie.py` edit must therefore run
  doughnut cases too. `demographics_grid.py` draws nothing itself and dispatches
  per cell through `render.plugins`, so a `bars.py` edit must also run any grid
  case whose cells are bars — the index records a grid case's cell builders, not
  just `demographics_grid`. Not a gate; it is the
  answer in the minute after an edit, and what keeps the suite in use between
  deploys.
- A hunt finding is **minimised** — one thing removed or shrunk at a time
  (categories, series, label length, slot size, then each setup back to default),
  keeping every change that still fails — then stored as a generated study plus
  one chart spec and promoted into the matrix, named for what it is
  ("stacked-h · 18 rows · 9in slot · 2 % sliver").

## Build order

The spec names several "first" tasks; this is the only sequence that works.
Everything in phase 1 is gating. Phases 2 and 3 can overlap.

1. **Make the run observable and honest.** `X-Preview-Path` (above). Close
   DuckDB connections at worker exit (blocker below). One-case runner
   `acceptance/run <case-id>`. Without these, nothing that follows can be trusted
   or debugged.
2. **Build the oracles against existing figures**, using the `Figure.savefig`
   seam (below) and the sweep enumeration in `scripts/chart_sweep.py`. Each
   oracle ships with a test feeding it a genuinely broken picture. No corpus
   needed yet.
3. **Settle the dpi question** (§Performance), **put worker recycling in place**
   (§How it runs), and **measure oracles 2–5 and re-size the matrix if they
   demand it** (precondition 7). All three must precede phase 4 — the last
   because a size cut after ~7,500 baselines are committed wastes exactly what
   the dpi item is sequenced to protect: dpi because adopting
   baselines first would commit ~7,500 pictures and ~23 MB of thumbnails that the
   change then invalidates — permanently, since PNGs do not delta-compress
   (§Risks); recycling because without it a worker's ~940 previews reach ~6.5 GB
   and the phase-4 run cannot complete at all.
4. **Build the corpus and the index**, then run the matrix rules-only, with no
   baselines, and adopt the pictures that pass every rule.
5. **Wire the gate** into the deploy script last, once a full run has been green
   twice.

Of the performance items, only the dpi decision is sequenced — and it is
sequenced because it moves pictures, not because the budget needs it. Memoising
the grouping derivation and the canvas-draw work are genuinely optional and may
land whenever. **Worker recycling is not optional**; draft 4 said it was, and the
measurement says otherwise.

## Blockers

**1. Memory that never comes back.** RSS grows ~6.6 MB per preview, linearly,
with no plateau — measured 320 MB → 1,902 MB over 240 previews, after
`gc.collect()`. It is not the data (`_PARSED` holds at most 4 DataFrames,
`api/model_loader.py:40`); it is per-render buffers freed into glibc arenas and
never returned — `fig.clear()` (`render/image/_mpl.py:307`) releases artists, not
RSS. **Mitigated, not fixed, by recycling workers** (§How it runs) — and the
recycling *is* gating: at ~940 previews a worker would otherwise reach
320 + 940 × 6.6 MB ≈ **6.5 GB**, ~52 GB across eight. Recycling every ~200 caps a
worker at 320 + 200 × 6.6 ≈ **1.64 GB**; that single figure is what §How it runs,
the sizing formula and precondition 6 are all derived from. Worth a real fix;
`MALLOC_ARENA_MAX=2` plus `malloc_trim` between previews is the cheap experiment.

**2. The process aborts at exit — diagnosed: an unclosed DuckDB connection.**
This one *is* gating. Any process that renders at least one preview and exits
normally dies with `terminate called without an active exception` — SIGABRT, exit
code 134, core dumped. The work completes first; the abort follows at teardown.

- **Mechanism**, from a gdb backtrace:
  `DuckDBPyConnection::~DuckDBPyConnection()` runs during finalization and calls
  back into the Python C-API (`PyEval_RestoreThread`); CPython 3.13 exits that
  thread, and `pthread_exit`'s forced unwind cannot propagate through the C++
  destructor frame → `std::terminate` → `abort`. `info threads` shows ~30 DuckDB
  workers parked and the aborting thread marked `(Exiting)`.
- **Site:** `stats/aggregate.py:7-17` keeps one connection per thread in
  `threading.local()`, deliberately never closed ("kept for the life of it"), and
  nothing in `src/` registers an `atexit`.
- **Proven remedy:** registering each connection at creation and closing it
  before exit turns 134 into 0, everything else identical. A real fix needs that
  registry plus an `atexit` — `threading.local()` cannot enumerate its own
  connections.
- **Ruled out**, each verified exiting 0: soffice alone, matplotlib alone, both
  together, python-pptx build and save, PIL text drawing, SAV parsing, template
  upload and analysis; also a thread-local connection on a joined worker thread
  and on a live daemon thread.

Invisible in a server that never exits, and invisible to the current suite (which
drives the engine on the main thread and exits 0). It bites a harness that exits
thousands of times, multiplied by recycling: crashed workers whatever their
assertions said, plus core dumps.

## Where the checks read from

Chart artists do not survive the request: `render_png` clears the figure after
saving and the PNG is unlinked once python-pptx has embedded it
(`_mpl.py:281-307`, `:669-676`). Chart text and slide text are different
materials, so each is read at its own seam.

**1. Chart interior — a `Figure.savefig` spy.** Draft 3 proposed a test-only hook
inside `render_png`. **No product change is needed:** monkeypatching
`Figure.savefig` gives exactly that window, and the existing tests already do it
(`tests/suite/unit/render/test_category_labels_never_overlap.py:126-168`).
Verified through the real endpoint — on a dense stacked bar the spy sees 72 texts
(70 `nsight-value`, 2 `nsight-group`), 84 Rectangles, 12 y-ticks, 6 x-ticks, a
legend and rotations [0, 90], with the figure fully populated.

**2. Slide surface — the python-pptx slide** handed to the compositor
(`routes_questions.py:1977`), plus the pure geometry helpers
(`measured_line_count`, `harvested_title_box`, `content_floor`, `footer_top`,
`fit_subtitle_size`). Title, subtitle and footer are shapes there
(`render/image/slide_chrome.py`) and become pixels only in the compositor:
`fast_preview.py:281` `compose_from_slide` → `:306` `ImageDraw.Draw` → `:609`
`draw.text`, measured with `draw.textlength` (`:598`, `:610`, `:633`). PIL, not
matplotlib — no artist exists to read.

**3. The served PNG** is the regression artifact and what a human looks at. Never
the source of geometry.

**Slides with no figure at all.** `themes` produces **0 savefig calls** —
measured. So do the four special slides. Every figure-based oracle skips them
silently; they are judged on seam 2 only, and the run asserts that each such case
produced zero figures rather than assuming it.

### The census — its own, not `_obstacles`'

Draft 3 said to walk `label_fit._obstacles`' census. **That is wrong**:
`_obstacles` (`label_fit.py:245-281`) is built to list what a category name must
not collide with, so it deliberately **skips the tick labels of any axis holding
the names being fitted** (`if (id(ax), axis) in named: continue`, `:272-274`) and
**excludes legends by design** (`:250-253`). Those are precisely oracle 1's first
rows and the defect in §Why. Built as specified, the oracle would be blind to
name↔name and legend collisions and pass everything.

The acceptance census is its own function, over every axes including twins:

- `ax.texts`, `ax.title`, **both tick-label sets unconditionally**, `ax.get_legend()`
  and `fig.legends`, `fig.texts`;
- **skip an axes whose axis is not drawn.** `ax.axison` is `False` after
  `ax.axis("off")` while its tick labels still report `get_visible() == True` with
  real text, on a builder that does exactly this (`render/image/wordcloud.py:127`,
  `:129`). Mutation-checked against the built oracle: dropping the filter makes a
  single axis-off figure contribute **14** phantom obstacles across its two
  tick-label sets. (An earlier note said 5; that counted `get_xticklabels()`
  only, and the census walks both sets.) `_obstacles` does not filter on this
  either; it is latent there, live here;
- `Annotation`s measured as bare text — unbound `Text.get_window_extent(t, r)`
  after `t.update_positions(r)` — because an annotation's extent wraps its leader
  line (`bars.py:1834-1846`). Line charts use 6 annotations for value labels, so
  this is not a stacked-bar special case;
- texts on blended transforms (group labels, `bars.py:683`, `:2192`) resolved
  through their own transform;
- tick labels read **after** `label_fit` rewrites them (`label_fit.py:102-128`).

### The collision geometry must be written

Draft 3 claimed to reuse "the separating-axes collision geometry" from two tests.
**Neither implements one.** `test_category_labels_never_overlap.py:114-121`
transforms the centre delta into rectangle *a*'s frame and compares half-extents,
ignoring *b*'s rotation — sound there because tick labels in one set share a
rotation, but not a separating-axis test. `test_value_labels_never_collide.py:86-88`
is a plain axis-aligned box intersection. A real SAT over both rectangles' axes
has to be written; a reference implementation is in
`work/ops/claude_oracle_cost.py`.

What those tests *do* provide, and what is genuinely reused: the `_oriented()`
rotate-to-flat trick for a rotated label's true box, the unbound
`Text.get_window_extent` rule, and the savefig seam itself.

## Scope

**In:** the preview a user sees — `POST /materials/{id}/preview-chart`
**with `render_title=False`** for every slide of every study on every template,
through the real app in-process; the image-mode builders; slide chrome; the
compositor and the LibreOffice path; grouping overrides and material curation;
ingest of real `.sav` files.

**Out:** AI-written text (themes bullets are stored ready-made; no model is ever
called); native-mode decks; the editor's own state handling beyond a small
browser smoke; hive behaviour (the harness uses the in-memory store).

## Corpus

### Studies (~25)

1. **Real, anonymised (16)** — one per staging study, pulled read-only, then
   anonymised from a fixed seed:
   - replaced: variable labels, value labels, open-text answers, customer and
     brand names, question wording;
   - preserved, because they are what breaks rendering: text **lengths** and line
     structure, non-ASCII and Finnish characters, variable and category counts,
     value distributions (perturbed ±2 %, re-rounded), missing-value patterns,
     unlabelled tick-boxes, scale shapes, battery structures, grouping overrides
     and curation;
   - **downsampled to ≤400 respondents**, ~2 MB each, ~30 MB total;
   - stored as real `.sav`, so `read_sav` and the whole ingest stay under test;
   - **checked, not hoped:** a test asserts no original string survives — every
     customer and brand name, every original label and open answer, from the
     pull's own record — and that the promised shapes did survive. Reproducible
     from its seed; the corpus is a committed artifact with its hash recorded.
2. **Existing (4)** — the three client SAVs in `input/` (tracked in git, so always
   present in a clone) and `testing/fixtures.synthetic_sav`, which is a
   5-respondent frame (`testing/fixtures.py:147-152`) and earns its place only as
   a degenerate case, not as a peer of the real studies.
3. **Invented (~6)**, generated by code, each for an extreme: a 40-statement
   battery; a classifier with 12+ groups; groups at and below `MIN_SEGMENT_BASE`;
   a 99/1 split; labels of 5, 40, 120, 250 characters; one-category and
   one-respondent studies; a multi-response set summing to 465 %; reverse-coded
   and 0–10 scales; duplicate and identical-prefix labels; a single unbroken
   60-character word; mixed scripts and emoji; values sitting exactly on the label
   cut-off and on the "fits inside its segment" boundary; negative means and a
   negative `net` row summary.

### The matrix is built, not exploded

**What "every chart type" means, counted:** 12 registry plugins
(`render/charts/`: combo, doughnut, funnel, horizontal_bar, line, pie, radar,
scatter, stacked_horizontal_bar, stacked_vertical_bar, vertical_bar, wordcloud),
each registering itself at import; plus 4 special slides (`special_overview`,
`special_conclusion`, `special_demographics`, `special_blank`), `themes`, and
`demographics_grid`, handled outside the registry in `model/report.py`.
**18 slide kinds**, and the run asserts it covered all 18 — a plugin added
without a matrix entry fails the gate rather than passing unseen.

Setup dimensions are **per chart type** — pie, doughnut and funnel use
`single_series_schema` (no Total, no Total position, no cross-tab,
`render/config_schema.py:366`); combo has no Total position; row summaries exist
on `stacked_horizontal_bar` only; scatter has two fields; a word cloud has
**none** — its single declared field is a `note_field` (`charts/wordcloud.py:28`),
informational text with no value to vary. The generator **enumerates the registry
at runtime** and reads each type's declared `config_schema`, so a new type or
option enters the matrix by existing — but it must **skip note-type fields**, or
it emits a valueless `note` dimension for every type that carries one.

Combination strategy, by what the defects actually are:

1. **Crossed fully** — the three things that drive crowding, because every defect
   this month was a four-to-six-way crowding interaction pairwise cannot
   construct: **slot geometry × density (rows, categories, series) × label
   length**, per chart type.
2. **All-pairs** over the remaining setup dimensions (statistic, base, Total,
   Total position, sort, formats, toggles, not-answered, empty categories, label
   overrides, row summary, classifier count, cross-tab layout, per-panel base),
   with **"absent" as a value** wherever a thing can be missing.
3. **Curated cases**, never sampled: every customer report, every hunt promotion,
   and the ones this month's defects came from.
4. **Legality first:** only what a study can express is emitted — scatter needs
   two numeric variables and its X/Y named, combo a numeric secondary, cross-tabs
   a second classifier, means a scale. Each rejection is recorded with its reason,
   and the count of pairs that could not be placed is reported, so a coverage
   claim is a number rather than a hope.

**The index is committed.** A seed pins a generator, not a matrix: the set moves
when a dimension gains a value, when legality changes, or when a library's
tie-breaking changes — orphaning every baseline at once. So the generator writes
`acceptance/index/*.jsonl`, one line per case with its id and full setup, and the
run reads that file and never calls the generator. Regenerating is a deliberate
commit whose diff shows which cases came and went. A case's id is a hash of **its
own non-default setup**, so a case that did not change keeps its id and its
baseline whatever else moved.

**Size, budgeted in seconds.** Sweep cases live in the same index, marked
`mode: sweep`, so the pre-flight guard counts them: a sweep that grows without
bound would otherwise blow the gate's budget from outside it. The index carries an
estimated cost per case (measured per chart type, refreshed each green run) and
the pre-flight sums **cost**, not rows: a stacked chart costs 3–7× a themes slide, and every case is
also judged. **Full tier: 6,000–7,500 cases.** Over budget, the run fails before
rendering with the biggest contributors named. Adding a study or template is
**two commits**: one raising the budget and saying why, then one adding it.

### Templates (~10)

Varying what the code actually reads (`template_profile.choose_layout`,
`template_check.theme_colours`, `style_spec.load_style_spec`):

- **slide count and layout usage** — 0, 4 and 20 slides, candidate and
  non-candidate layouts (`template_profile.py:492-530`);
- **theme colours** — `lt1`/`dk1`/`accent1-6`, including the stock-Office set that
  is deliberately rejected (`style_spec.py:24-36`), and a `clrMap` override;
- **a ≥75 %-area backdrop shape** (`template_profile.py:47`) — the only "dark
  background" the renderer sees;
- **harvested title style** — run vs master `titleStyle` vs theme, with caps, line
  spacing and alignment, a white title on a dark ground
  (`resolved_style.py:95-107`), **and at least one template whose title is not
  `positioned`**, which is the case that breaks header-based path detection;
- **content-area share above and below 40 %**, chart slots small, wide, tall and
  narrow (chosen by area, `style_spec.py:238-242`);
- **furniture harvesting** — repeat-share (`template_profile.py:55`), logo and
  backdrop areas (`:58`, `:47`), the 60-character rule (`:717`);
- the customer templates, anonymised, and the house default.

Not generated, because nothing reads them: page aspect, palettes beyond
accent1-6, slot offset as such, and a font the host lacks.

## Oracles

Every oracle names the types it applies to. A type absent from its table is a gap
the run reports — once per kind, with a count and one example.

### 1. Overlap — the first duty

| Pair | Verdict |
|---|---|
| text ↔ text (any two) | never overlap; names keep 0.2 em clear each side |
| a number ↔ the bar/slice it belongs to | expected |
| a number ↔ any other bar, slice or its numbers | never |
| a callout ↔ its own leader line | expected |
| a leader line ↔ another number's box | never |
| legend ↔ plot area, bars, slices | never |
| legend ↔ its own handles | expected |
| title / subtitle / footer ↔ the chart picture | never |
| gridline, axis, spine ↔ anything | ignored |
| text ↔ its own text box | must fit inside it |

**Applies to:** all 12 chart plugins and every `demographics_grid` cell, with
stated exceptions — a **word cloud**'s words are an `imshow`'d raster, not texts,
and overlap *is* its form (`render/image/wordcloud.py:110-129`); **pie/doughnut** labels sit on
a curve and thin wedges' numbers are deliberately outside the axes on leader lines
(`render/image/pie.py:274-285`, `:341-355`); **scatter**'s point labels are offset
annotations that legitimately crowd (`render/image/scatter.py:47-54`).

**These are exceptions to this oracle only, and they are not alike.** A word cloud
and scatter are exempt from oracles 2 and 3 as well, so they are judged by oracles
4, 5 and 6. **Pie and doughnut are not exempt** — oracle 2 judges them with their
own computed floor and oracle 3 on wedge geometry; only their *label overlap* is
excepted here, because the labels sit on a curve. Build the exemption table from
each oracle's own "Applies to", never from this paragraph. The 4 special slides
and `themes` have no figure and are judged on seam 2.

**`demographics_grid` is judged as charts, not chrome** — each cell renders a
compact chart for its own question (`model/report.py:196-199`), so one slide
carries several; each gets the full check, and cells are also checked against each
other across cell boundaries.

**Classification needs gids the product does not set.** Telling "a number ↔ its
own bar" (expected) from "a number ↔ another bar" (a defect) requires knowing
which texts are value labels. **This is now done** — and the count this spec used
to give was wrong three times over, so here is the measured one.

`VALUE_GID` lives in `render/image/_mpl.py`, not in `bars.py`: every builder
draws values and every builder already imports `_mpl`, whereas reaching into a
peer builder for a constant is a dependency pointing the wrong way.
`bars._VALUE_GID` remains as an alias, because two existing test modules import
it from there.

**Eight genuine value-label sites exist. Seven are tagged**, each driven by a
test watched failing first (`tests/suite/unit/render/test_value_labels_carry_their_gid.py`):

| module | sites | note |
|---|---|---|
| `bars.py` | `:1250`, `:1376` | the clustered paths; stacked already had gids |
| `line.py` | `:61` | offset annotation |
| `funnel.py` | `:74` | |
| `combo.py` | `:80`, `:139` | `:139` draws on a twin `ax2` — why the census must cover twins |
| `pie.py` | the `autopct` loop | matplotlib makes these, so they are tagged after `ax.pie` returns |

**Two are deliberately untagged**, and both were miscounted before:

- `pie.py:274`, the thin-wedge callout. It is a real value label, but no fixture
  yet draws one — a 2 % sliver under the 4 % floor produced *no* text at all when
  measured, so tagging it would be production code no test watches.
- `scatter.py:54` annotates each point with its **category name**, not a value.
  Scatter has no value labels; tagging it would be wrong.

The earlier "11 sites" also counted `funnel.py:89` (a category label), pie's
`"n = 500"` base (`:214`) and pie's invisible `alpha=0.0` measuring artist
(`:240`, removed before `savefig`). `radar.py` and `wordcloud.py` draw no value
labels; `demographics_grid.py` draws nothing itself and inherits whatever its
cells' builders do. It is a **classification** gap, not a census one — the census
walks every text regardless.

### 2. Completeness

**Applies to:** 10 of the 12 plugins and `demographics_grid` cells; not the
special slides or `themes`. **Not a word cloud** — its words are an `imshow`'d
RGBA array (`render/image/wordcloud.py:110-126`) with no `Text` artists at all,
so "every category named" has nothing to read. **Not scatter**, whose points
carry labels but no categories, series or legend in this sense. Those two are
judged by oracles 4 and 5 only, as oracles 1 and 3 also state.

Every category named; every group's n shown where the chart splits by a group;
every value above the author's cut-off printed somewhere; legend entries matching
the series drawn.

**The cut-off is computed, never assumed.** `label_floor(fmt, *, default_pct,
axis_max=100.0)` (`_mpl.py:534`, keyword-only) returns a *share of the value
axis*, and the author's own cut-off wins when set. Defaults come from
`LABEL_FLOOR_DEFAULT_PCT` (`:522-525`): pie and doughnut 4.0, every other type the
1.0 fallback (`:526`). The oracle calls it with the case's own number format and
axis max — right for a stacked chart's 1 % slivers, not only pie wedges.

Stated exceptions, all deliberate: a wedge below the computed floor carries no
number (`pie.py:62`, `:294`); a battery's statements carry no n, not being groups
(`bars.py:558`); n is suppressed at base 0 (`_mpl.py:50-57`); `clear_callouts` may
leave out a number with nowhere clear to go (`bars.py:1942-1947`) — counted per
chart, failing only above a stated budget.

**Cutting:** no two rows of one chart may truncate to the same string **where a
distinguishing tail exists** (`cap_keeping_tail`, `label_fit.py:198-220`). Where
none exists, it is recorded as a known limitation, not a failure.

### 3. Truthfulness — the picture agrees with the data

**Applies to:** bar, column, stacked (both), line, combo, and `demographics_grid`
cells. Pie/doughnut/funnel are judged on wedge and stage geometry with their own
floors; radar, scatter and word cloud on containment and legibility only.

- **Proportion, against the scale the chart declares:** where `_stack_scaling`
  normalises (`bars.py:1461-1495`), each segment's width ÷ its bar's total must
  match the value's share of that total; otherwise width equals the value. The
  printed label is compared with the engine's value **separately**, because on a
  normalised stack the two deliberately disagree (`bars.py:2021-2024`).
- **Axis:** the limit is `_value_axis(max_val, statistic)` (`bars.py:243-269`),
  widened by `final_axis_max` when a row summary is present. Every drawn value
  lies within it. A negative value — which the hard 0 floor clips — is a defect.
- **Order:** categories and series as the sort asks, manual included.
- **Colour:** one colour per series within a chart — except small multiples, which
  key colours by position across panels (`bars.py:813-815`), and palettes that
  wrap when series outnumber colours (`house_style.py:280-283`). Muting of "not
  answered" is checked on clustered bars and pie, where it is real
  (`bars.py:1232`, `pie.py:369`), not on stacked.
- **Counts:** a printed n equals the engine's base for that group; the slide's N
  footer equals `base_n["Total"]` except where the product says otherwise
  (`elements.n=False`, a `footer_note` override, comparison charts).

### 4. Containment and legibility

**Applies to:** all 18 slide kinds, as do oracles 5 and 6. For the special slides
and `themes` it runs on seam 2 alone.

Everything inside its slot — **on seam 2**. Draft 6 said "nothing clipped" of the
chart figure too; that cannot happen there. `render_png` saves with
`bbox_inches="tight"` (`_mpl.py:305`), which GROWS the canvas to hold every
artist, so an overflowing label makes the picture smaller inside its slot rather
than losing anything. Containment is a slide question.

**There is no single font floor, and the two this spec used to name were wrong.**
The renderers enforce five, per path:

| constant | pt | governs |
|---|---|---|
| `label_fit._MIN_PT` | 7.5 | category names |
| `bars._VALUE_LABEL_MIN_PT` | 7.5 | vertical-bar value labels |
| `bars._GROUP_BLOCK_MIN_FS` | 7.5 | group block labels |
| `bars._VALUE_MIN_PT` | 6.5 | the stacked shrink floor |
| `bars.py:1367`, inline `max(5.5, …)` | 5.5 | clustered-horizontal value labels |

plus `bars._MIN_LABEL_BAR_PT` (5.0), which decides whether a label is drawn at
all. The customer's own clustered bar draws at **5.5 pt** — measured — so a rule
encoding "6.5 pt numbers" would fail a correct chart on its first run. The 5.5
has no named constant, which is worth fixing while implementing this.

**Choosing the right floor per text needs the gid work** (§Oracle 1): the floor
depends on what kind of text it is, and only `bars.py` tags its texts. Until then
the honest rule is the weakest true one — **nothing below 5.0 pt**, which still
catches type collapsing away — and the per-kind version lands with the gids.

**Contrast** is checked on declared colours **where a declared fill exists** — a
number inside its bar or wedge (`contrast_ink`), text on the resolved ground. A
chart is saved transparent (`_mpl.py:305-306`) and composited onto a rasterised
ground, so text over that region has no declared fill and is **sampled from the
pixels**. The funnel's white-on-teal (`render/image/funnel.py:73-79`) and the
hardcoded spine colour (`bars.py:426`) are known fixed colours, not failures.

### 5. Agreement

**Applies to:** all 18 kinds; the preview-vs-deck comparison is sampled.

- **Preview vs deck:** the chart picture region of both at the same dpi, with a
  small tolerance (two rasterisers, anti-aliasing); the same texts with the same
  wrapping and cuts; the same placement within the slot.
- **Across templates:** the same chart shows the same numbers and category names
  on all 10; wrapping, cuts, sizes and colours may differ. A number that
  disappears on one template only is a defect unless a stated exception explains
  it, and the report says which.

### 6. Behaviour and cost

**Applies to:** every case, all 18 kinds.

The endpoint converts internal exceptions into a 422 (`routes_questions.py:2017-2021`),
though `except HTTPException: raise` (`:2015`) passes through the 503 (`:1847`)
and the scatter guard (`:1852-1856`) unchanged — the latter's fixed detail text is
a model for the list below. "No 500s" is therefore unfalsifiable. Instead:

- every generated case answers **200 with a PNG**;
- a 422 fails **unless** the case is on a short named list of expected refusals,
  and then its *detail text* must match what that list says. An unexpected 422 is
  a crash until its wording proves otherwise;
- a **503** means the image has no LibreOffice and fails the run outright;
- **`X-Preview-Path` is `composited` on every case.** A `libreoffice` reading
  fails: a different rasteriser is a different picture, and it means a ground
  build failed;
- **every worker exits 0** (blocker 2);
- LibreOffice conversion has per-pid profile isolation (`export/pdf_convert.py:52`)
  and a 120 s timeout (`:108`); a case that times out fails as a case. A failed
  case is re-run once, alone: if it then passes it is reported as **flaky** by
  name and never silently passed. One flaky case does not fail the run; **more
  than 3, or any case flaky on two consecutive runs, does** — a threshold rather
  than a judgement call, because it decides whether the stamp is written at all;
- per-preview time within a budget set from the first green full run
  (provisionally p95 ≤ 2 s, mean ≤ 1 s) and then held.

### Rules are themselves tested

Each oracle has a test feeding it a picture that really is broken, asserting it
complains. Without that, a gate that passes everything looks exactly like a gate
that works. Given B3 above, the overlap oracle's own test must include a
name↔name collision and a legend↔name collision specifically.

## Baselines

- **The rules are the verdict. The digest is a change detector.** A case is
  **failed** when a rule fails. A case whose rules all pass but whose image digest
  moved is reported **changed**, never failed, and a human decides. A run with
  changed cases and no failures is **green but unapproved**: the deploy gate
  requires green *and* no unapproved changes, so an intended redesign is
  acknowledged rather than silently shipped.
- **The digest is of the full-size image.** A greyscale thumbnail cannot see
  "4 %2 %" or a colour change.
- **The thumbnail is what a human looks at** — committed beside the digest
  (~3 KB, ~23 MB at 7,500 cases), with its exact recipe recorded.
- **One file per case** under `acceptance/baselines/<case-id>.json`, so two
  approvals collide only when they concern the same picture.
- **Approval history per case:** previous digest, new digest, reason, and the
  commit responsible. An approval touching more than fifty cases must name the
  change and link that commit.
- **Approval commits touch `acceptance/baselines/` and nothing else**, so a bisect
  can skip them mechanically.
- **First run has no baselines and asks for none:** rules are the verdict, and a
  case passing every rule adopts its own picture. Human review at first acceptance
  is the contact sheets — every distinct combination once, everything flagged, a
  random sample.
- **A case new to a regenerated index is `new` — a third state, proposed not
  adopted.** It has no baseline, so it is neither *failed* nor *changed* and would
  otherwise slip through the split above mid-life. If every rule passes, the run
  writes its picture as a **proposed** baseline (`"proposed": true` in
  `acceptance/baselines/<case-id>.json`) and the stamp lists it in its own
  **new-case list**, separate from the changed list. A proposed baseline is not an
  approved one: the gate refuses while any remain (§Gate mechanics). A human
  clears them with one acknowledging commit that drops the `proposed` flag, after
  reviewing them on the contact sheet — no re-run required. This is what stops a
  regenerated index quietly adding 400 self-approving cases.
- **Validity is bounded by what changes pictures**, recorded by image digest plus
  `fc-list`: Python 3.13.7, matplotlib 3.10.9, Pillow 12.2.0 **with raqm**,
  matplotlib's bundled freetype 2.6.1, **the compositor's own text stack** (PIL's
  freetype 2.14.3, harfbuzz 13.2.1, raqm 0.10.3 — a second stack, distinct from
  matplotlib's, and including fribidi 1.0.16), wordcloud 1.9.6, python-pptx 1.0.2, pyreadstat 1.3.5, numpy
  2.4.6, pandas 3.0.3, LibreOffice 25.8.7.3, and the font set
  (`fonts.rendering_fingerprint()` — the image ships `fonts-dejavu`,
  `fonts-liberation`, `fonts-inter`).
- **Determinism self-check every run:** a fixed sample drawn twice in separate
  workers must be byte-identical, with that case's cache entry cleared first and
  the log confirming it was drawn, not served (`routes_questions.py:1918-1921`).
  A failure is reported before anything else, because the baselines then mean
  nothing.

## How it runs

- **Its own image** (`acceptance/Dockerfile`): pinned Python, matplotlib, Pillow,
  poppler, LibreOffice and fonts.
- **In-process, no network:** the real app over an in-memory object store, as
  `tests/suite/conftest.py::client_memory` wires it — but **without** that suite's
  autouse parsed-SAV reset (`conftest.py:149-157`).
- **One shared cache root, per-worker TMPDIR.** Per-worker cache dirs would
  rebuild each template's ground per worker — 10 × 8 × ~6 s = **8 of the 20
  minutes** on LibreOffice alone. The ground cache is content-keyed on template
  source, mtime, dpi, slide and slot geometry, colours and
  `rendering_fingerprint()` (`fast_preview.py:45`), so sharing is safe. `TMPDIR`
  stays per worker (`ground_image` builds through `tempfile.mkdtemp`, `:96`;
  `render_png` uses `tempfile.mkstemp`, `_mpl.py:281`), and both are set **before
  the app is imported** because `_CACHE = cache_dirs.ground_root()` binds at import
  (`:41`). The run asserts `cache_dirs`' temp-dir fallback (`cache_dirs.py:48-56`)
  did not fire and cleans up after itself (~473 MB of preview PNGs per full run at
  a median 63 KB).
- **The rendered-preview cache must stay cold, by assertion.** It is keyed on
  `_PREVIEW_CACHE_SALT`, a fresh `uuid4()` per process only while
  `NSIGHT_DATAHIVE_URL` is unset (`routes_questions.py:1677-1680`). That is the
  harness's configuration, so today it is cold **by accident**. Set that variable
  and the salt becomes a stable code digest, a re-run serves yesterday's pictures,
  and the gate silently passes everything. The run asserts it is unset.
- **Workers recycled, and the re-parse counted.** At ~7,500 cases over 8 workers a
  worker renders ~940 previews; recycling every ~200 caps it at
  320 + 200 × 6.6 ≈ **1.64 GB**. But `_PARSED` is process memory (`_PARSED_MAX = 4`,
  `model_loader.py:40`), so each recycle re-parses the studies that worker owns —
  ~350 ms each (`model_loader.py:26`). With study partitioning (~3 studies per
  worker) that is ~1 s per recycle, ~5 recycles per worker: ~40 s of startup plus
  ~40 s of re-parse across the run, ~10 s of wall time. Draft 3 claimed "parse
  once per worker" and budgeted no re-parse term; both are corrected here.
- **A process-pool runner, not xdist.** `pytest-xdist` is absent, and its
  scheduling does not naturally express study partitioning or worker recycling.
  Worker count is fixed and recorded, sized `floor((free RAM − 2 GB) / 1.7 GB)`
  — the 1.64 GB recycling cap plus a little headroom, deliberately, so a worker
  running slightly over its cap does not oversubscribe the box — never sensed per
  run. Note the formula's consequence: **8 workers need ≥ 15.6 GB free**, not the
  13.1 GB the cap alone implies.
- **Grounds warmed serially before the timed run** into the shared cache
  (`ground_image`, `:74`, ~6 s each, ~60 s total), so every case is composited and
  the non-atomic ground write cannot race.
- **LibreOffice bounded globally:** `NSIGHT_SOFFICE_WORKERS=1`. The soffice pool is
  per-process with no global cap (`_MAX_CONCURRENT`, defaulting to
  `workers_for(6)` = `min(6, cores−1)`), so without the variable 8 workers × 6
  slots × ~300 MB is 14 GB if anything stampedes onto that path. Setting it to 1
  also reduces the import-time profile-dir loop (`pdf_convert.py:57-60`) to **one
  dir per PID**: ~40 dirs per run at 8 workers × ~5 recycles, against ~240
  without. Those are swept only by a 24 h cleanup that skips live PIDs
  (`cleanup.py:155`) and misbehaves when PIDs recycle fast, so creating slots
  lazily — or pointing `profile_root()` at a per-run directory the harness deletes
  — remains worthwhile hygiene, just not the thousands-of-directories problem
  draft 4 described.
- **Font substitution runs in its own phase**, never interleaved: it writes host
  fontconfig and moves the fingerprint that keys every cache (`fonts.py:86-92`,
  `:310-345`). The run asserts the fingerprint is unchanged between start and end.
- **Determinism:** fixed seeds (word clouds already use `random_state=42`), fixed
  fonts, fixed dpi, no clock in any renderer, no AI.
- **Placement:** `acceptance/` at the repo root. A bare `pytest` never collects it
  (`testpaths = ["tests"]`); its own config must repeat `pythonpath = ["src"]` and
  `asyncio_mode = "auto"` or nothing imports.
- **One case, one command:** `acceptance/run <case-id>` renders that preview alone,
  in seconds, writing the picture, its baseline, the difference and the failing
  rule's own measurements. Built in phase 1.
- **Quarantine:** a case can be quarantined with a reason, an owner and an expiry.
  It still runs and is still judged; it just does not redden the gate, and when its
  date passes it does again. The report opens with how many are quarantined and
  which expire this week.
- **Reports:** a self-contained folder (HTML index, contact sheets, failures with
  pictures) in a gitignored directory. Every failure carries a stable id — study ·
  template **content hash** · question · chart type · slot · digest of non-default
  setup · rule · **rule version**.
- **Browser smoke:** a handful of studies opened in the real editor (Playwright, as
  `scripts/e2e` does), checking the pictures arrive and match the backend's bytes.

## Gate mechanics

A green run writes a stamp recording the acceptance image, the matrix index hash,
a hash of exactly the files a deploy would send — `scripts/deploy/` rsyncs the
**working tree**, not a commit — **and the list of changed cases**. Without that
list the deploy script cannot evaluate the condition it is asked to enforce.

The deploy script refuses unless the stamp matches and **both** its changed-case
list and its new-case list are empty, printing the command to run;
`--no-acceptance` overrides it and is echoed into the deploy log. The run starts
**before** the deploy window opens.

**Three states, two lists, one clearing action each.** There is no separate
"approved" flag to look for:

| state | what the run wrote | what clears it |
|---|---|---|
| **failed** | nothing | fix the defect |
| **changed** | nothing; the old baseline stands | a commit replacing the digest in `acceptance/baselines/<case-id>.json` |
| **new** | a baseline marked `"proposed": true` | a commit dropping the `proposed` flag |

In both cleared cases the case becomes simply *unchanged* on the next run, and
its list is empty. The distinction that matters: a **changed** case has a human
baseline to compare against and the run will not overwrite it; a **new** case has
none, so the run proposes one rather than adopting it, and a human still has to
say yes. Either way the deploy is blocked until someone has looked.

## Performance

**The budget is met without optimisation.** At the real size: 7,500 × 0.85 s ÷ 8
workers ≈ **13.3 min** (6,000 ≈ 10.6 min), plus a measured **0.6 min** of overlap
checking, plus ~1 min of ground warming and worker churn ≈ **15 min**. Required
throughput is 5.0–6.25 previews/s, not the 8.33 draft 3 carried over from the
retired 10,000-case matrix.

**Oracle cost, measured** (`work/ops/claude_oracle_cost.py`), per chart:

| texts | pairs | extents | pairwise | total |
|---|---|---|---|---|
| 50 | 1,225 | 12.6 ms | 2.9 ms | 15.5 ms |
| 100 | 4,950 | 24.8 ms | 13.2 ms | **38.0 ms** |
| 200 | 19,900 | 52.3 ms | 54.2 ms | 106.5 ms |
| 400 | 79,800 | 117.2 ms | 220.5 ms | 337.7 ms |

A dense stacked bar carries ~90 artists to test — the 72 value and group texts the
census measured, plus its 18 tick labels — so 38 ms/case → ~0.6 min across 8
workers.
Extents scale linearly; the pairwise term is quadratic and overtakes them past
N≈200, where a grid or interval index is needed. This covers **oracle 1 only**;
oracles 2–5 read patch geometry and byte digests rather than shaping text, and
are cheaper, but they are **not yet measured** — measure before fixing the size.

Measured per-stage cost on 60 real slides in 36.0 s (stages overlap):

| stage | total | % | per call |
|---|---|---|---|
| build_presentation (chart render + pptx) | 20.85 s | 58.0 % | 347.5 ms |
| mpl.savefig (chart PNG, dpi=200) | 7.36 s | 20.5 % | 147.2 ms |
| mpl.canvas.draw | 7.33 s | 20.4 % | 23.2 ms × 316 |
| PIL.save (final preview PNG) | 6.66 s | 18.5 % | 60.5 ms |
| model + grouping override | 6.48 s | 18.0 % | 107.9 ms |
| compose_from_slide (PIL composite) | 5.51 s | 15.3 % | 91.8 ms |
| PIL.resize (LANCZOS) | 5.10 s | 14.2 % | 51.0 ms |
| pptx.Presentation (parse template) | 2.23 s | 6.2 % | 37.2 ms |

Optional, in value order — **none is required for the budget**:

1. **Render the chart at the dpi it is composited at.** `render_png` saves at
   `dpi=200` (`_mpl.py:305`); the compositor's default is 110
   (`fast_preview.py:281`). Measured: the slot needs 1367×548 px, the chart is
   rendered 2485×996 — **3.3× the pixels** — then LANCZOS-downscaled
   (`_paste_picture`, `fast_preview.py:319`). savefig 20.5 % + resize 14.2 % ≈ 34 %
   of the run. **It changes what the picture looks like**, so the decision must be
   made before baselines are adopted even though the saving is no longer needed.
2. **Memoise the grouping derivation.** `df_model_for_material` →
   `apply_grouping_override` → `suggest_indicator_families`
   (`ingest/multi_group.py:160`) costs 107.9 ms on every preview, **18 %**. It is a
   pure function of `(model, df)` and the override is constant for a report, yet it
   is recomputed per chart — the mistake `model_loader.py:26` already diagnoses
   one layer up.
3. **Stop drawing the whole figure to measure a string.** `text_size_in_data`
   (`bars.py:1757`) and `text_width_in_data` (`:1771`) call `canvas.draw()` per
   measured string, as does `pie.py:242`; `label_fit` re-measures on every setting
   it tries (`:113-128`). Draws per chart: stacked_horizontal 40.7 (55.6 % of its
   render time), stacked_vertical 26.0, pie 6.0, others 3.0. The honest A/B on 60
   real slides is **33.6 s → 31.7 s, 6 %**, because only 4 of 60 are stacked; on a
   uniform 12-type matrix roughly **16 %**.

`template_cache._resolve`'s `lru_cache(maxsize=16)` is keyed per template file and
already exceeds the ~10 templates here, so it needs nothing — but it must be
raised if the corpus ever passes 16 templates, or it silently starts re-resolving.

**Caching that would weaken the test**, forbidden: the rendered preview cache
(above); reusing a rendered chart across templates, when the template axis exists
precisely because a template changes every measurement; and dropping
`rendering_fingerprint()` from any key — it hashes the installed font families
(`render/fonts.py:310`) and ties a baseline to the image.

## Preconditions for the twenty minutes

1. DuckDB connections closed before each worker exits (blocker 2) — **gating**.
2. `render_title=False` on every request, and `X-Preview-Path` asserted
   `composited` — **gating**.
3. One shared cache root, all grounds pre-warmed serially before the timed run.
4. Studies partitioned across workers, so the 4-entry SAV cache never thrashes,
   with the re-parse term counted.
5. Workers recycled every ~200 previews to cap RSS at ~1.64 GB — **gating**,
   not an optimisation.
6. 8 workers with **≥ 15.6 GB** genuinely free — that is what
   `floor((free − 2) / 1.7) = 8` requires, and provisioning the 15.12 GB that
   8 × 1.64 GB + 2 GB suggests yields only **7** workers, which costs ~2 min on
   the render term and makes every §Performance timing wrong. The 2 GB reserve
   also carries the soffice peak (up to 8 processes during oracle 5's sampled
   comparisons). **This host does not have that today** — 3.8 GB available with
   23 GB of swap in use — so the acceptance image needs a machine that does, and
   the run records what it had.
7. Oracles 2–5 measured. The size stands at 6,000–7,500 on oracle 1's measured
   cost alone; measuring the rest may force it down. That measurement and any
   re-sizing are **phase 3 work**, listed there, and must land before phase 4
   builds the index.

## Non-goals

Pixel-perfect agreement with PowerPoint; testing LibreOffice itself; the editor's
UI beyond the smoke; replacing the existing suites.

## Risks

- **False alarms** erode trust faster than missed defects: every rule ships with
  its own proof and states its own tolerance. The `ax.axison` filter and the
  `_obstacles` correction above exist because the first two false-alarm sources
  were found before a line was written.
- **Baseline churn:** an intended change flags many cases. Handled by the
  failed/changed/new split above — and note that orphaned baselines are the other
  half of churn: when a regenerated index drops a case, its
  `acceptance/baselines/<case-id>.json` and thumbnail are **deleted in the same
  commit as the index change**, or the directory grows without bound in a repo
  this section is already watching for size.
- **Corpus in git:** ~30 MB of studies, ~23 MB of thumbnails; PNGs do not delta-
  compress, so each broad approval adds most of that again, permanently.
  Approvals are on master only and watched per update.
- **Anonymisation must not sand off the sharp edges** — the long Finnish statements
  and odd characters are the point; its own test checks they survived.

## Done when

- The matrix runs green in the acceptance image **within its stated budget** (≤20
  min, currently projected ~15) and the deploy script enforces it, refusing while
  either the changed-case or the new-case list is non-empty.
- Sweeps and hunt run, and at least one real defect found by them is fixed and
  pinned in the matrix.
- Every oracle has a test proving it catches a broken picture, including
  name↔name and legend collisions.
- `acceptance/run <case-id>` answers in seconds.
