# Generated vs original — data / chart-style / information amount

Judged from side-by-side renders (`cmp_*.png` = original | generated). Only the slides that
have a real original counterpart are compared; the 13 "variety" styles (slope, dumbbell,
heatmap, treemap, word cloud, tornado, …) have NO original — they are extra views, not part
of the comparison.

| Slide | Data coverage | Chart style | Information amount |
|---|---|---|---|
| **Aided awareness** | equal — 9 providers × 4 waves both | **mine cleaner** (monochrome ramp, current wave bold) vs original's 4 hues | ~equal (original adds tiny ±wave deltas) |
| **General opinion** | chart equal (private/public × 5 levels) | **mine better** (red→green diverging + KIELT/MYÖNT zones) | **ORIGINAL MORE** — shows positive-% across prior waves *(touko 25: 55%, marras 24: 57%…)* + a "Muutos toukokuusta" change column; mine has neither |
| **Brand-image (Attendo)** | **original more** — 14 attrs × **4 waves**; mine = current wave only | mine cleaner (sorted, negatives flagged) | **ORIGINAL MORE** (4-wave trend per attribute) |
| **Radar profiles** | **original more** — current + a prior-wave (Touko 2025) radar; mine = current only | **mine MUCH better** (readable small-multiples vs an 8-line tangle) | original denser but unreadable; mine clearer, single wave |
| **Word list** | **original much more** — wordcloud + TOP-10 for **all 4 waves**; mine = current wave | trade-off (mine adds sentiment colour) | **ORIGINAL MORE** |

## The pattern (the real answer)
- **Chart style / readability / correctness: generated ≥ original on every slide.** Numbers are
  exact; the radar is dramatically more legible; palettes are clearer.
- **Information amount: the original wins.** nSight's signature is **multi-wave trend density** on
  nearly every slide — the metric shown across all 4 waves, plus change deltas / change columns.
  My generated slides (except awareness) **collapse to the current wave**, trading information
  for cleanliness. So per-slide, the original carries more.
- The **20-slide variety deck is thinner still** — its 13 variety slides are single-metric,
  single-view by design, and it reuses ~4 datasets, so deck-wide it covers far fewer metrics
  than the original's 56 slides.

## Why, and the fix (it's a description + data problem, not a tooling limit)
My descriptions mostly asked for the **current wave**; the 4-wave data already exists
(`original_data.json` etc.). The generators can render multi-wave + deltas just as cleanly —
the awareness slide proves it. To match the original's information amount: write the
descriptions to **require the trend across waves + the change-vs-last-wave figure** (and, where
the original has them, segment cuts), and feed the prior-wave data. Then the generated slides
would be as information-dense as nSight's **and** cleaner.

**Bottom line:** as charts, the generated output is as good or better and exact; as
*information-per-slide and breadth*, it currently **under-delivers vs the original** — fixable by
richer descriptions + the wave/delta data, not by changing tools.

## After densification — generated now matches/exceeds the original's information amount
Re-issued the descriptions to REQUIRE multi-wave trend + change, supplied the prior-wave data
(extracted from the deck), and regenerated via agents. Judged renders:

| Slide | Original carried | Dense generated now carries | Verdict |
|---|---|---|---|
| Aided awareness | 4 waves + small deltas | 4 waves + **"Muutos toukokuusta" change column** (±0/+1/−1…) | **matches+** |
| General opinion | current + positive-trend text + change col | current 5-level stacked + **4-wave positive sparklines** + +6%/+3% change badges | **matches+** |
| Brand image (Attendo) | 14 attrs × 4 waves | 14 attrs × **4 waves** ramp + **change column** + negatives flagged (matala=hyvä) | **matches+** |
| Word list | wordcloud + TOP-10 × 4 waves | **TOP-10 × 4 waves** + sentiment colour + connector lines showing movement | **matches+** |

Files: `work/agent_dense_{awareness,opinion,brandimage,words}.pptx` (reusable scripts
`chart_lab/agent_dense_*.py`). Iterations: 1 each, except **brand-image = 2** (my data-extraction
bug — I'd handed it the wrong adjacent chart; the agent correctly refused to fabricate waves,
I fixed the extraction, it passed). 

**Outcome:** information density now meets the original on all four core slides — and exceeds it
(sentiment, change columns, readable trend), while keeping exact numbers and cleaner styling.
