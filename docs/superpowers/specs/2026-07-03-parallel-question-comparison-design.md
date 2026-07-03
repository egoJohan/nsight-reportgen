# Parallel-question comparison (radar / grouped bar of several multis or batteries)

## Goal
Overlay SEVERAL parallel questions as multi-series on one chart — one series per question.
The reported case: brand-image adjectives, each a MULTI-response question ("Which news
services fit *Rohkea*/*Luotettava*/…?", options = services). The customer wants one radar
comparing adjectives across the service axes. Customer: "Näihin tulee useasta eri
multi-muuttujasta arvoja (adjektiivit — vertailtavat palvelut)."

## Key framing (why it's not a radar hack)
A comparison is a GRID: `series (adjective) × category (service)` with a value per cell. That
grid renders as a radar (one polygon per series) OR grouped/clustered bars (clusters =
categories, series = adjectives) — the chart type is just how it's drawn. So build it at the
DATA layer as a standard multi-series `SeriesResult` (categories = axes, segments = series);
the radar + clustered-bar renderers already consume that shape.

## Current state (verified)
- `_battery_comparison` ALREADY does this — but only for **rating batteries**: `_parallel_
  batteries` auto-detects batteries sharing the same attribute label-set and overlays them
  (categories = attributes, segments = entities/brands, cell = MEAN). Routed only for
  `kind=="battery"` + `chart_type=="radar"`.
- A **multi** on a radar goes through `_multi` → categories = its options, segments =
  `("Total",)` → exactly ONE polygon. No way to add sibling multis.
- No control anywhere to choose WHICH parallel questions are series.

This is the multi-response twin of the battery radar. So: **generalise the comparison**, don't
special-case radar; keep it distinct from GROUPING (grouping COMBINES variables into one
question — this OVERLAYS separate questions as series).

## Design

### Part A — engine: generalise the comparison
- `_parallel_questions(question, model)`: all questions of the SAME kind whose category set
  matches — battery: member ATTRIBUTE labels (existing `_parallel_batteries`); multi: member
  OPTION labels. Order-independent, EXACT set match (conservative: only auto-overlay
  questions that truly share the axes). Explicit `series_refs` (Part B) is LENIENT instead —
  it aligns by label and fills any category a series lacks with 0/None, so a hand-picked
  series with a near-miss option set still charts.
- `_comparison(question, spec, data, model, refs=None)`: builds the multi-series grid.
  - `categories` = the shared category set (axes), in `question`'s order.
  - `segments` = one per parallel question, labelled by its DISTINGUISHING text
    (`_series_label`). NOTE: the position differs — batteries put the entity at the HEAD
    ("Attendo — Arvioi…" → "Attendo", today's `_entity_label`), but the adjective multis put
    it at the TAIL ("…ominaisuuksiin? -Rohkea" → "Rohkea"). So derive it robustly: strip the
    COMMON prefix AND common suffix shared by all the parallel questions' texts, and the
    remaining differing fragment is the series label. This ONE rule UNIFIES both kinds
    (battery entity via common SUFFIX; multi adjective via the tail), so it REPLACES the
    head-only `_entity_label` in the comparison path (keep `_entity_label` for its other
    callers). Falls back to the full text when there is no clean common part.
  - cell(category, series) = battery → MEAN on the shared scale (existing); multi → the %
    of respondents who ticked that option (as `_multi` computes).
  - `refs` (optional) overrides auto-detection with an explicit series list (see Part B).
- Routing in `compute`: for a comparison-capable chart type (`radar`; later `vertical_bar`/
  `horizontal_bar`) on a battery OR multi, use `_comparison` when there is >1 series (auto)
  or an explicit series list. `_battery_comparison` becomes a thin battery-branch of it.

### Part B — generic "Compare with" series control
- `spec.options["series_refs"]`: the EXPLICIT, ordered set of series question refs —
  INCLUDING this chart's own question (always first/implied; deduped). Empty/absent →
  AUTO-detect (all parallel questions). Present → use exactly those (manual trim/extend).
  The chart's own question is always a series even if omitted from the list. Same field for
  battery + multi radars. Refs that aren't compatible (different category set) are ignored.
- Config schema: a `series_refs` multi-select ("Compare with") on the comparison-capable
  chart schemas (radar, clustered bar), listing questions that share this question's
  category set. Defaults (in the UI) to the auto-detected set so it's pre-populated and
  trimmable — matching the chosen "auto-detect + manual trim".
- COST — this is NOT just a schema line. Today's config widgets are `select / switch /
  variable / numeric_variable`; there is NO multi-select-of-QUESTIONS widget (existing ones
  pick VARIABLES from `/variables`, not question refs). Part B therefore needs: (a) a new
  widget type (e.g. `question_multiselect`) in the frontend registry, and (b) a source of
  COMPATIBLE questions to offer — the backend exposing, per question, the refs that share
  its category set (a small `/questions` addition or a dedicated endpoint). This is why
  Part B is Phase 2; Phase 1 (auto-detect, zero config) already gives the customer the radar.
- Serde: `series_refs` round-trips in `options` (already free-form).

### Part C — rendering (mostly free)
- Radar already draws one polygon per segment → works unchanged.
- Grouped/clustered bar already draws multi-series → the SAME comparison grid renders as
  clusters (categories) × series (adjectives). So a comparison is chartable as radar OR
  grouped bar with no per-renderer work — the genericity payoff.

## Testing (TDD)
- `_parallel_questions`: matches multis by option-set; matches batteries by attribute-set;
  does NOT match questions with a different category set.
- `_comparison`: multi case → categories = shared options, one segment per multi, cell = the
  multi's %; battery case unchanged (means). Explicit `series_refs` overrides auto-detect.
- Routing: multi + radar with ≥2 parallel multis → comparison (multi-series); a lone multi →
  single-series (unchanged). Battery radar unchanged.
- Schema/serde: `series_refs` exposed on radar + clustered-bar; round-trips.
- Render smoke: radar of 3 parallel multis draws 3 polygons; the same series render as a
  grouped bar.

## Phasing
- **Phase 1**: engine `_parallel_questions`/`_comparison` for multis + auto-detect routing on
  radar (unify `_battery_comparison`). Makes the customer's radar work with zero config.
- **Phase 2**: the generic `series_refs` "Compare with" control (manual trim/add) + expose
  comparison on the clustered-bar chart types (radar → bar genericity).

## Risks / open items
- **Series labelling**: a multi's distinguishing text (the adjective) must be extractable
  from its question text; if the text isn't in a "…- Adjective" shape, fall back to the full
  text (long legend). The manual label/rename path (question rename) can fix stragglers.
- **Category alignment**: parallel questions may not list options in the same order or have
  identical option sets (a service missing for one adjective) — align by label, fill missing
  cells as 0/None (as `_battery_comparison` already does).
- **Auto-detect breadth**: many parallel multis → many polygons (cluttered radar). The manual
  trim (Part B) is the escape hatch; auto-detect should cap/warn if it overlays a lot.
- **Battery-radar regression**: switching the comparison's series label from `_entity_label`
  (head) to the common-strip must leave the EXISTING brand-battery radar unchanged. For
  "Attendo — Arvioi X" the strip yields "Attendo" (same), but verify against the Attendo
  golden deck and update it only if the new label is genuinely better; keep `_battery_
  comparison`'s means/base identical.
