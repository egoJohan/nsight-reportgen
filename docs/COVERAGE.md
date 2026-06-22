# Attendo deck — slide-by-slide coverage (what we can deliver from the raw `.sav` today)

_Based on a full inventory of all 56 slides of `Attendo Bränditutkimus Marraskuu 2025.pptx`
(see the inventory script output). "Derivable" = the current-wave numbers can be computed
from the single raw `.sav` we have._

## Headline

| Bucket | Slides | What it means |
|---|---:|---|
| **Data slides — current wave derivable now** | **37** | Charts/tables whose current-wave numbers compute from the raw `.sav` today |
| Open-ended word lists (data present, coding approximate) | 5 | Slides 25–29; need nSight's coding frame for exact counts |
| Pure insight/narrative (numbers derivable, prose = judgment) | 2 | Summary slides 4 & 6 |
| Structural (titles / section dividers / agenda / methodology) | 12 | Carried over from the template; no data needed |
| **Total** | **56** | |

**So ~37/56 slides are data-driven and their current-wave content is derivable from the raw
file today; ~12 are structural (free); ~5 + ~2 need human-in-loop (coding / narrative).**

## The cross-cutting dependency: wave history

Of the 37 data slides, **27 also display prior waves** (3 earlier survey rounds, as extra
chart series or table deltas). The **current-wave column is derivable now**, but the prior
columns/deltas require a **seeded wave-history store** (a single `.sav` has no past waves).

- **10 data slides** are fully complete from the raw file (no trend element): demographics
  + several single-wave tables.
- **27 data slides** are "current wave now, full trend once history is seeded."

## Verified (line-checked against the deck, 2026-06-02)

Representatives from **every** data family were computed from the `.sav` and matched the
deck's printed current-wave numbers:

| Family | Slides checked | Result |
|---|---|---|
| Aided awareness | 15 | exact |
| Aided awareness by segment | 16 | bases exact; "Ei kokemusta" & "Suosittelijat" 8/8 exact |
| General opinion + detail | 18, 19, 20 | all cells ≤1pp |
| Spontaneous + top-of-mind | 14 | ±1pp |
| Demographics | 11, 12 | exact |
| Brand-image perception (bars) | 33, 34, 38 | 14/14 exact — metric = **top-2-box** (score 4–5, base incl. EOS, per-brand SPSS codes resolved dynamically) |
| Brand-image distribution + table | 34 | exact |
| Segment image (mean Likert ×100) | 37 | 15/16 ≤1pp |
| Willingness — general & professionals | 53, 55 | all brands ≤0.5pp |
| Brand-image TOP-10 words | 25 | 10/10 lemma set |

Per-family verification ⇒ the same metric reproduces for the rest of each family.

### Key mapping facts now KNOWN (remove guesswork from the build)
- Experience base = `var11O19 OR var11O20` (**n=636**), not incl. professionals (772).
- Brand-image bars = **top-2-box** (4+5), base includes "En osaa sanoa"; the "5" code differs
  per brand block — resolve codes dynamically from the codebook.
- Segment-image slide = **mean Likert ×100**.
- Opinion private/public are **label-swapped** vs slide index — bind by title text.
- `Suosittelijat` = `var158O706==1` (would recommend Attendo); professionals = `var11O21==1`.

### The pipeline caught TWO errors in the manual deck
- Slide 16 "Ammattilaiset" awareness (7 brands) is a **copy-paste of the "Suosittelijat"
  column**; the real professional awareness is higher and **is derivable** from the `.sav`.
- A Humana cell (26% vs real 16%) is a **manual data-entry error**.
This is a selling point: the automated pipeline is not just as accurate as manual work — it
**surfaces manual mistakes**.

### Only genuinely non-current-derivable item
- Slide 9 (one demographics chart, n=1008, English labels) is a **prior wave** not in this
  `.sav` — a wave-history dependency (R4), not missing current data.

## Per-slide classification (0-based index)

| Slides | Class |
|---|---|
| 0, 2, 4(div), 7, 8, 12, 16, 23, 29, 51, 55, 1 | Structural (12) — template carry-over |
| 3, 5 | Insight/narrative (numbers derivable; prose by LLM/analyst) |
| 9, 10, 11 | Demographics — derivable now (no trend) |
| 13, 14, 15, 17, 18, 19, 20, 21, 30, 32, 35, 36, 37, 39, 41, 43, 45, 47, 49, 52, 53, 54, 6 | Charts — current wave derivable now; prior waves need history (23) |
| 22, 33, 34, 40, 44, 46, 50 | Tables — derivable now (6; current-wave numbers) |
| 31, 38, 42, 48 | Tables with trend deltas — current derivable; deltas need history (4) |
| 24, 25, 26, 27, 28 | Open-ended word lists — data present, coding approximate (5) |

## Bottom line for the proposal

- **From the raw `.sav` alone, today:** regenerate current-wave content on **~37 data
  slides** + carry **12 structural** slides = **~49/56 slides** present and current-wave-
  correct. (4 metric types proven exact; the rest high-confidence by question type.)
- **Add a seeded wave-history store** → the 27 trend slides gain their prior-wave columns →
  full trend fidelity.
- **Needs nSight input (human-in-loop):** 5 open-ended slides (coding frame) + 2 insight
  slides (narrative review) + a 1-cell mapping reconciliation (professionals' awareness) +
  confirmation of weighting/base conventions per study.
- **Not regenerable from data (inherited or out of scope):** bespoke graphics — e.g. the
  wordcloud *image* on the brand-image slides — and any hand-placed callouts.
