# Risks to delivering a high-quality nSight prototype deck

_Goal of the phase: auto-generate a presentation with real value that closely resembles
what nSight produces manually (Attendo brand tracker as the target)._

Each risk below is grounded in something actually encountered while building the prototype,
not generic. Ordered by how decisively it threatens the goal.

---

## R1 (RE-ASSESSED — was flagged CRITICAL, now LOW/MEDIUM after verification)
**Original claim (WRONG):** the per-segment aided-awareness slide (deck slide 16) was
thought to need bases (608/245/234/257) that couldn't be reproduced from the `.sav`.
**What verification actually showed:** that slide holds **four charts, one per wave**;
608/245/234/257 is a *prior* wave. For the **current** wave the segment bases reproduce
**exactly** from the raw `.sav`:
- Kokemusta omaavat = **636** (experience-question routing base)
- Ei kokemusta = **229** (`var11O22`)
- Ammattilaiset = **216** (`var11O21`, works/worked in care)
- Suosittelijat = **249** (`var158O706`, would recommend Attendo)

And the segment-split awareness numbers match the deck **24/32 within ±1pp** — *"Ei
kokemusta"* and *"Suosittelijat"* are **8/8 exact**, *"Kokemusta omaavat"* 7/8.
**So the derived populations ARE in the file; the data IS available.** The original
"not derivable" was an analysis error (comparing to the wrong wave).

**Residual (the real, smaller risk): variable-mapping reconciliation.** The
*"Ammattilaiset"* non-Attendo awareness column diverges — professionals computed from the
data show *higher* awareness (e.g. Validia 61% vs deck 32%), while the deck column nearly
duplicates the "experienced" column. That is either a deck artifact or a different source
variable (professionals also have a dedicated `var159` block) — a *which-variable-feeds-
this-cell* question, NOT missing data.
**Impact:** low — most segment content is directly derivable. **Mitigation:** a one-time
mapping reconciliation with nSight for a handful of cells (and confirmation of weighting/
base conventions); ideally their analysis spec to lock edge cases. Not a go/no-go blocker.

## R2 (HIGH) — Manual analyst coding can't be fully reproduced mechanically
**Evidence:** open-ended brand-image words. The engine reaches 10/10 on the TOP-10 lemma
*set*, but the deck's *counts* differ because nSight did manual thematic merging (e.g.
"suuri" folded into "iso") beyond inflection/synonym rules. "Kiire" vs the deck's
"Kiire/kiireinen" label is another manual edit.
**Impact:** verbatim/open-ended slides will be *approximately* right, visibly off on exact
numbers/labels a reviewer would notice.
**Mitigation:** treat open-ended coding as human-in-the-loop (capture nSight's coding frame),
or scope these slides as "assisted," and score them on ranked overlap not exact counts.

## R3 (HIGH) — The deck's real value is the insight narrative, which is analyst judgment
**Evidence:** the high-value slides are the summaries ("Attendo on edelleen selvästi
tunnetuin…", what moved, what it means). Gemini (via egoHive) can draft a correct one-line
key message from verified numbers — proven live — but full multi-point insight slides with
*correct emphasis and nuance* are unproven.
**Impact:** auto-generated insights risk being generic or subtly wrong, which is exactly
where "real value" lives. Over-claiming here is the reputational risk.
**Mitigation:** constrain prose to verified numbers (already done — numbers never come from
the LLM); human review of narrative; evaluate prose quality with nSight before promising it.

## R4 (HIGH) — Trend/wave history is not in the data file
**Evidence:** the charts show 4 waves; we only "reproduced" prior waves by reading them out
of the original `.pptx`. The raw `.sav` is a single wave.
**Impact:** for a genuinely new wave, prior-wave numbers must come from a maintained store;
otherwise every trend slide (a large share of the deck) can't be populated.
**Mitigation:** stand up a wave-history store fed each wave (datahive can hold this); seed it
from past decks once. First real run needs that seeding.

## R5 (MEDIUM-HIGH) — Coverage effort + brittle template binding
**Evidence:** 4 slide types regenerated+verified; each needed individual investigation
(find variables, read deck ground truth, golden test, bind shapes). Shape binding is by
name, and 4 slides have **duplicate/generic shape names** ("Content Placeholder 9" ×4).
**Impact:** a full 56-slide deck is significant per-study manual setup; bindings are fragile
to template/questionnaire changes.
**Mitigation:** budget realistic per-slide effort; add stable shape tagging to the template;
accept per-study-type setup cost. Prioritize high-value slides for the prototype.

## R6 (MEDIUM) — Non-data visual elements can't be regenerated, only inherited
**Evidence:** slide 25 carries a **wordcloud image** (a Picture, not a chart); decks also use
manually placed callouts/arrows and per-point color coding.
**Impact:** if nSight expects these refreshed each wave, they're a gap (we can refresh chart
data + tables + text, not bespoke graphics).
**Mitigation:** scope explicitly which elements are data-refreshed vs template-inherited; a
wordcloud-image generator would be separate work.

## R7 (MEDIUM) — Methodology (weighting) must be captured per study
**Evidence:** Attendo matched **unweighted** (no weight variable in the file). That is
Attendo-specific; other trackers/studies are typically weighted.
**Impact:** wrong weighting → every percentage off. Generalizing beyond Attendo needs the
weighting scheme per study.
**Mitigation:** capture the weighting spec per study; we already have a validation method
(reproduce one known chart weighted vs unweighted).

## R8 (MEDIUM) — Generalization beyond Attendo is per-study engineering
**Evidence:** everything is Attendo-specific variable bindings. Loyalty (NPS) and
segmentation (cluster models baked into the `.sav`) are structurally different.
**Impact:** the prototype proves the brand tracker; the *offering* needs each study type
built, with segmentation the hardest.
**Mitigation:** position the prototype as the brand-tracker vertical; estimate each further
study type separately.

## R9 (MEDIUM) — Platform integration is not turnkey yet
**Evidence:** datahive ingest crashed on a dated `.sav` (we fixed it); datahive has **no MCP
tool for cross-tab aggregation** (we read the DuckDB store directly, which contends with the
server's lock); egoHive needed **manual Postgres inserts** to stand up an agent because the
product-deploy happy-path needs the builder UI; auth was non-obvious (`custom_jwt`/`DEV_AUTH`).
**Impact:** "uses egoHive + datahive" is real but required workarounds; productionizing needs
engineering on the platforms themselves.
**Mitigation:** budget for: a datahive server-side tabular-aggregation tool, proper agent
provisioning via egoHive's normal flow, ingest hardening.

## R10 (LOW-MEDIUM) — SPSS export variability
**Evidence:** the aided-awareness `var18` multi-response grid worked once decoded, but value
codes/missing conventions/multi-response encodings differ across questions and will differ
across surveys.
**Impact:** each new survey export needs codebook mapping; no guarantee of consistent
structure even within nSight's own studies.
**Mitigation:** codebook-driven mapping (built) + a per-study binding step; request a
consistent export convention from nSight.

---

## Re-assessed: is the raw `.sav` enough? (verified)
Earlier this was framed as a critical go/no-go (R1). **Verification refuted that.** The
current-wave content — including the segment splits once thought underivable — reproduces
from the raw `.sav`: aided awareness exact, general opinion exact, spontaneous ±1pp, and
segment bases + 2 of 4 segment-awareness series **exactly**. So the raw `.sav` carries
most of the deck's substance.

What still genuinely needs nSight (now the top risks, in order): **R4** prior-wave history
(not in a single-wave file), **R2/R3** open-ended coding + insight narrative (analyst
judgment), and a **one-time variable-mapping reconciliation** for a few edge cells
(professionals' awareness, weighting/base conventions). These are scoping items, not a
data-availability wall.

## What is already de-risked (proven in the build)
- **Data availability — VERIFIED across every slide family** (2026-06-02): demographics,
  experience, aided awareness, awareness-by-segment, general opinion + detail, brand-image
  perception (top-2-box) + distribution + segment-mean, spontaneous + top-of-mind,
  willingness (general + professionals), open-ended TOP-10. Representatives line-matched the
  deck (mostly exact). The earlier "not derivable" fear is fully retired.
- **The pipeline caught two manual-deck errors** (a copy-pasted awareness column; a
  mistyped Humana cell) — accuracy *exceeds* manual in those cases.
- Rendering into nSight's exact template (native charts/tables/text), preserving styling.
- Live prose generation via **egoHive/Gemini** from verified numbers.
- **datahive** verified able to store + serve the data (codebook via MCP, rows round-trip).
- A fidelity harness + construction proof that objectively measure "resembles the deck".
- **Net: the dominant remaining data dependency is wave history (R4)**, plus human-in-loop
  for open-ended coding + insight narrative, plus per-study mapping/weighting confirmation.
