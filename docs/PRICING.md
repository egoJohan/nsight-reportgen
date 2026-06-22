# nSight deck-automation — Proof-of-Concept proposal (fixed price)

## Purpose
Prove that nSight's manual deck production **can be productized** — that survey data can be
turned automatically into the right charts and narrative, in nSight's own template, using
**egoHive (agent/Gemini) + datahive (data plane)**. The PoC deliberately **does not** meet
final production quality; it demonstrates feasibility on **3 focused use cases**.

## Fixed price: **€4,800**
Single fixed fee, ~4–5 working days. This is achievable at this price because the hard,
risky parts are **already built and verified** (see `COVERAGE.md` / `RISKS.md`): the data
engine reproduces the deck's numbers exactly across every slide family, rendering into the
real template works, the egoHive/Gemini prose path is live, and datahive is confirmed as the
data plane. The PoC packages this into a clean, repeatable, demoable proof.

## The 3 use cases (what the PoC proves)

**UC1 — Accurate data → charts, sourced via datahive.**
Ingest the Attendo `.sav` through datahive; auto-regenerate **2 chart slides** (aided
awareness + general opinion) into nSight's template, with numbers **matching the original
deck exactly**. Proves: the data plane + deterministic accuracy (no LLM in the numbers).

**UC2 — Agentic insight, via egoHive/Gemini.**
The Finnish key-message on a slide is written **live by Gemini through egoHive** from the
verified numbers. Proves: the agent layer works, and numbers stay deterministic while prose
is automated.

**UC3 — A second metric type + objective quality measure.**
Regenerate a **brand-image perception slide** (a different metric — top-2-box) and produce a
**fidelity score** comparing generated vs original, plus the **construction proof** (blank
the data, rebuild it from the `.sav`). Proves: it generalizes across metric types and quality
is **objectively measurable** — and the same harness already **caught two errors in nSight's
manual deck**, showing value beyond parity.

## Deliverables
1. A runnable **web demo**: pick the `.sav` + brief → generate a small multi-slide `.pptx` →
   see the fidelity score → download the deck.
2. The generated `.pptx` (subset of slides) + a side-by-side fidelity comparison vs the
   original.
3. A short **PoC report**: what was proven, the verified numbers, the productization
   architecture (egoHive + datahive + nSight engine), and the risks/scope for a full build.

## Explicitly NOT in the PoC (kept out to hold the price)
- Final production quality / pixel-perfect polish.
- The full 56-slide deck — only the ~4 slides across the 3 use cases.
- Wave/trend history (prior-wave columns), open-ended-coding accuracy, demographics breadth.
- Other study types (loyalty, segmentation).
- Productionization: SLAs, hardening, auth, deployment, datahive MCP aggregation tool.

## Assumptions
- Scope frozen to the above 3 use cases on the Attendo brand tracker.
- Access to the running egoHive + datahive instances (available).
- Visual style = the fixed Attendo template; bespoke graphics inherited, not regenerated.

## What comes after (for context, not part of this fee)
A full production build (all 56 slides resembling the manual deck, seeded trends, all
metrics, insight narrative, web app, light hardening) is a **separate phase** estimated at
~6–8 weeks; indicative range **€40k–52k** depending on hardening scope and the agreed day
rate. The PoC is the gate that justifies committing to it.
