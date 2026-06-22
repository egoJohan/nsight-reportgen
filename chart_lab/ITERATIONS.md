# Agent-generation iteration log

Process: I write a free-text description from the original → a builder AGENT generates the
slide from description + data (its own script/design; never sees the original) → I render and
judge (visual + content vs original) → feed fixes → repeat. Goal: few iterations + one generic
reusable generator per chart type.

| # | Chart type | Generic generator | Iterations to approve | Judge verdict |
|---|---|---|---|---|
| 1 | Grouped horizontal bar (multi-wave) | agent_build_awareness.py | **1** | approved — sorted, teal wave-ramp, current wave bold, n+caption+legend; exact |
| 2 | 100% stacked perception bar | agent_build_opinion.py | **1** | approved — diverging palette, KIELT/MYÖNT zones, 57/58% positive callouts; exact |
| 3 | Perception-profile radar | agent_build_radar.py | **1** | approved — small multiples vs average, numbered key, negatives flagged; exact |
| 4 | Trend (multi-line) | agent_build_trend.py | **1** | approved — leaders emphasised, direct end labels de-collided, null wave handled; exact |
| 5 | Brand-image word list | agent_build_words.py | **1** | approved — ranked, sentiment-coloured, legend, n; exact |

Average iterations to approve: **1.0** (5/5 first-pass approvals).

All five generators are reusable/parameterised → they generalise to the deck's other slides of
the same type (e.g. willingness & by-segment reuse the grouped-bar generator; opinion-detail
reuses the stacked generator; brand-image-per-competitor reuses a single-series bar variant).

## Remaining slide types (still to generate the same way)
- Demographics (donut/bar) — slides ~10-12
- Single-series perception bar / top-2-box (brand image per competitor) — slides ~32-51
- Data tables — several slides
- Section dividers / title / agenda — structural, no chart (~12 slides)

## Batch 2 — toward ~20 slides
| # | Chart type / piece | Generator | Iterations | Verdict |
|---|---|---|---|---|
| 6 | Brand-image bar (per provider ×8) | agent_build_brandimage.py | **1** | approved — positives sorted, negatives flagged "matala=hyvä"; exact per-brand |
| 7 | Structural (title + 7 dividers) | agent_build_structural.py | **1** | approved — polished title, consistent dividers |
| 8 | Deck assembly (20 slides, ordered) | agent_assemble_deck.py | **1** | merged, 20 pages, charts survived |

**Running total: 20-slide deck `work/attendo_agent_deck.pptx`. Average iterations to approve: 1.0 across all 8 generators/pieces (8/8 first-pass).**

## Batch 3 — 20 DATA slides, maximize distinct chart styles (no structural filler)
Three builder agents produced 13 new distinct styles; assembled with the existing approved
charts into `work/attendo_agent_deck20.pptx` (20 slides).

| Group | New styles | Iterations |
|---|---|---|
| Awareness variety | slope, dumbbell, lollipop, bump/rank, bar+avg-line, vertical columns | **1** |
| Brand-image variety | heatmap, clustered dot plot, net-diverging bar, grouped 3-brand bar | **1** |
| Words/opinion variety | word cloud, treemap, tornado/diverging | **1** |
| 20-slide assembly | — | **1** |

Judge-checked in render: heatmap, treemap, tornado, bump/rank, dot plot — all clean, exact,
distinct. Agents self-checked the remainder.

### Final 20-slide deck — ~18 distinct chart styles/layouts
grouped multi-wave bar · vertical columns · lollipop · bar+average-line · multi-line trend ·
slope · dumbbell · bump/rank · 100% stacked diverging · tornado/butterfly · radar small-multiples ·
heatmap · clustered dot plot · net-diverging bar · grouped 3-brand bar · single-series sorted bar
(×2 brands) · sentiment-ranked bar · word cloud · treemap.

**Overall: every generator/piece approved first pass — average 1.0 iterations.**

## Fix (judge-caught after review)
- **Heatmap (deck slide 12)** — initially approved on render, but on the user's review two
  overlaps surfaced ("Kielteiset" group label vs column headers; colourbar vs the Esperi row).
  Builder agent fixed both (raised group labels above headers; moved colourbar below all rows)
  and re-assembled. **Heatmap total: 2 iterations.** All other 19 slides remain 1 iteration.

## Batch 4 — new CONTENT (breadth, not just style)
Extracted prior-unused metrics from the deck and generated via agents (description + data → build → judge):

| Content | Style | Generator | Iterations | Verdict |
|---|---|---|---|---|
| Spontaneous awareness (top-of-mind) | horizontal stacked | agent_content_spontaneous.py | **1** | approved — top-of-mind + muut = total, sorted, exact; 10%-named-none footnoted |
| Willingness to choose/recommend | grouped 4-wave bar + change col | agent_content_willingness.py | **1** | approved — sorted, current emphasis, change pills, opt-out separated, exact |
| Respondent demographics | donut + columns + bar (NEW style: donut) | agent_content_demographics.py | **1** | approved — gender/age/region, exact |

Adds 3 new metrics (closing the breadth gap) + the donut style. Files:
`work/agent_content_{spontaneous,willingness,demographics}.pptx`.
