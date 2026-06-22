# Chart generation — judged iteration log

**Goal:** prove a free way to generate beautiful, production-grade, correct charts for a
customer deliverable, by driving the use case, comparing to the original, and judging the
output visually — looping until approvable.

**Free stack used (no license, no browser/Node):**
- **Altair / Vega-Lite** (declarative charts) + **vl-convert** (Rust, headless) → **SVG + PNG**.
- LibreOffice + `pdftoppm` to render the *original* slide to PNG as the visual benchmark.
- Generator: `chart_lab/gen.py` (parameterised; `uv run python chart_lab/gen.py <ver>`).

**Use case:** the aided-awareness chart (slide 15), grouped horizontal bars, 9 brands × 4
survey waves. Charts plot the original chart's **exact** numbers, so the comparison isolates
*visual* quality. Numbers in real production come from the verified tabulation engine.

## Files to view
- `original_slide-15.png` — nSight's original chart (benchmark).
- `v1.png … v4.png` (+ `.svg`) — the iterations.
- **`v4.png` / `v4.svg` — the approved output.**

## Iteration log (generate → view → judge → fix)

| Ver | What I saw (judged from the rendered PNG) | Fix |
|---|---|---|
| **v1** | **Broken:** title, brand labels, legend labels and data labels all *missing* — only gridlines + "%" rendered. Cause: font `Arial` not installed; vl-convert renders unknown fonts blank. | Switch font to **Liberation Sans** (installed; Arial-metric-compatible). |
| **v2** | All text restored. Clean, on-brand, sorted, clear bottom legend, current-wave labels only. Beautiful, non-overlapping. Gap vs original: only the latest wave's values were labeled. | Label **all** waves (completeness, like the original) — and test for overlap. |
| **v3** | All 36 values labeled, colour-matched to bars, **zero overlap**. Complete + far more legible than the original. Nit: amber (Toukokuu 2025) labels are the lowest-contrast on cream. | Consistent **dark-ink** labels; emphasise the current wave. |
| **v4** | **Approved.** All values labeled in consistent ink; **current wave bold** so it reads instantly; uniform legibility; zero overlap; clear legend; correct values; crisp vector. | — |

## v4 vs the original — verdict

| Criterion | Original | v4 |
|---|---|---|
| Values correct | ✓ (benchmark) | ✓ exact match |
| Non-overlapping | labels tiny & crowded | ✓ clean, every value pinned to its bar |
| Legend clarity | ✓ | ✓ |
| Legibility / emphasis | uniform tiny labels | ✓ muted history + **bold current wave** |
| On-brand look | nSight house style | ✓ matches (cream, palette, sorted bars) |
| Output quality | raster in the deck | **vector SVG** — crisp at any zoom / print |

**Verdict: v4 is approvable** and is *better than the original* on legibility while keeping
full completeness.

## What this proves for production
The free Vega-Lite → SVG path produces production-grade, correct, non-overlapping charts,
themable to nSight's house style, with text-measured auto-layout (the thing native PowerPoint
charts can't guarantee). SVG embeds crisply into the deck. Next steps to productionise:
1. Promote the v4 theme into a reusable **archetype** (one of the chart-component library).
2. Add the **render-and-verify** backstop (render → overlap/legibility check → auto-fix/flag).
3. Build the remaining archetypes (stacked perception, radar, trend, word list) the same way.

---

# Archetype 2 — perception (100% stacked horizontal bar), slide 18

Source: general-opinion chart (`BAR_STACKED_100`), private/public × 5 opinion levels.
Tool: **Altair/Vega-Lite → SVG**. Files: `stacked_s1..s3.png/.svg`. **Approved: `stacked_s3`.**

| Ver | Judged | Fix |
|---|---|---|
| s1 | clean stacked bar, diverging **red→green** palette (positive reads instantly — fixes the original's green=bad/blue=good), per-segment label contrast handled. Missing the headline "positive %" callout. | add positive callout |
| s2 | callout added but **y category labels dropped** (axis=None on layers suppressed the shared y-axis); also hit Vega parse errors (layered duplicate axes; d3 format can't embed literal text → precompute label strings; stack `normalize`→`zero` + x headroom for the callout). | restore y-axis on bars only |
| **s3** | **Approved.** category labels back, in-bar % labels, right-side "▸ 57/58 % myönt." callout, clear legend, correct values, no overlap. Better than the original (clearer palette + callout). | — |

# Archetype 3 — perception profile (radar), slide 31

Source: 14 attributes × 8 brands. Vega-Lite has **no radar** → tool: **matplotlib (polar) → SVG**.
Files: `radar_r1` (overlaid) and `radar_sm1` (small multiples). **Approved: `radar_sm1`.**

| Ver | Judged |
|---|---|
| r1 (overlaid, all 8 brands) | cleaner than the original (thin lines, no heavy fills, wrapped labels) but 8 lines still **tangle** — not high enough quality. |
| **sm1 (small multiples)** | **Approved.** one mini-radar per brand vs a dashed all-brand average; numbered spokes + a key handle the 14 long labels; each profile instantly readable; reproduces the slide's own insight (Onnikodit's large profile) — **decisively beats** the original tangle. |

# Overall verdict & the "best free way"

Three core chart types built from scratch, themed to nSight, judged against the originals —
**all approved, all at least as good or better than the manual originals.**

- **Primary engine: Altair/Vega-Lite → SVG (vl-convert)** for bar / grouped-bar / stacked —
  text-measured auto-layout, clean theming, no overlap, crisp vector. Free, headless.
- **matplotlib → SVG** for **radar** (Vega-Lite has no radar) and other polar/bespoke needs.
- Both free, deterministic, export **vector SVG** that embeds crisply into the deck.
- Key practical gotchas learned (all fixed): use an **installed font** (Liberation Sans /
  DejaVu Sans, not Arial); in layered Vega-Lite charts only **one layer** declares each axis;
  d3 number formats **can't embed literal text** (precompute label strings); for "too many
  series" charts (radar), **small multiples** beat overlay.

Approved deliverables to view: **`v4`** (grouped bar), **`stacked_s3`** (perception),
**`radar_sm1`** (profile). Remaining archetypes for full coverage: trend line, word list.

---

# Archetype 4 — trend (multi-line, wave-over-wave)

Source: aided awareness across 4 waves. Tool: **Altair/Vega-Lite → SVG**. **Approved: `trend_t1`.**
Two leaders (Attendo/Esperi) emphasised (thick, coloured, points); the other 7 muted grey;
**direct end-labels** instead of a legend; missing first wave (Validia) handled. Clean, instantly
readable — the right technique for many time series.

# Archetype 5 — brand-image word list (sentiment-ranked bar)

Source: slide-25 spontaneous TOP-10 (Attendo, n=863). Tool: **Altair/Vega-Lite → SVG**.
**Approved: `words_w2`.** Ranked by count, **coloured by sentiment** (kielteinen/myönteinen/
neutraali) with counts + legend — adds insight a plain text list/wordcloud can't: Attendo's
image is dominated by negatives (Kallis 185, Huono, Kiireinen, Ahne). (w1 dropped the word
labels via the same axis=None pitfall; fixed in w2.)

# FINAL — archetype library complete (5/5 deck chart types)

| # | Archetype | Tool | Approved file | vs original |
|---|---|---|---|---|
| 1 | Grouped horizontal bar (awareness) | Vega-Lite→SVG | `v4` | cleaner labels, no overlap |
| 2 | 100% stacked perception bar | Vega-Lite→SVG | `stacked_s3` | clearer palette + positive callout |
| 3 | Perception-profile radar | matplotlib→SVG | `radar_sm1` | small-multiples beat the tangle |
| 4 | Trend (multi-line) | Vega-Lite→SVG | `trend_t1` | emphasise+direct labels |
| 5 | Brand-image word list | Vega-Lite→SVG | `words_w2` | sentiment colour adds insight |

All free, headless, deterministic, **vector SVG**, themed to nSight, and judged **≥ the manual
originals**. This is the production chart-component library: Vega-Lite for cartesian charts,
matplotlib for polar/bespoke. Next: theme-config consolidation + the render-and-verify backstop,
then wire into the deck-generation pipeline.
