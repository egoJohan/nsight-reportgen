# R3 rendering spike — GO/NO-GO decision

_Date: 2026-06-22 · Decision: **GO — native rendering is the primary path.**_

The spike (plan Phase 1, Tasks 1.0–1.4) tested the project's highest unknown: can the tool
build editable native PowerPoint charts **de-novo** (`add_chart` + raw-OOXML `c:manualLayout`
+ data-label positions) that are valid, survive LibreOffice→PDF conversion, and render
cleanly? This determines whether `render_mode` defaults to **native** (editable) or **image**.

## Evidence (three signals)

| Signal | Result | Source |
|---|---|---|
| **1. Valid, editable OOXML** — de-novo `add_chart` + injected `c:manualLayout` (plot-area box) + `c:dLbls`/`c:dLblPos val="outEnd"` produce a deck that **reopens without error**, contains a real `c:chart` (not a picture), and carries the correct series values. | **GREEN** | Task 1.2 (`54d87ea`): 6/6 tests incl. the save+reopen gate; review verified the injected XML against ECMA-376 `CT_PlotArea`/`CT_BarChart`/`CT_ManualLayout` tag sequences — no schema fixup was needed. |
| **2. Numbers survive LibreOffice conversion** — the native chart's data labels render as real text in the converted PDF. | **GREEN** | Task 1.4 (`87dcbf3`): `test_spike_numbers_survive_pdf` extracted **all five** data-label values (28/34/18/13/7) from the LibreOffice-converted PDF via pdfplumber within ±0.5. |
| **3. Layout judged clean** — Claude judges the rendered chart for overlapping/truncated labels. | **DEFERRED** | Task 1.4 wired `test_spike_layout_judged_clean` (`@pytest.mark.judge`, R3-LAYOUT rubric). `ANTHROPIC_API_KEY` is not set in this environment, so it **skips**. It runs in the keyed CI judge lane (plan Task 9.5). |

## Decision: GO (native primary)

Two of three signals are GREEN **objectively** (structural feasibility + numerical fidelity
through the full PPT→PDF pipeline). The third (visual cleanliness) is a *quality* signal, not
a *feasibility* one, and is deferred to the keyed CI lane rather than blocking.

**Consequences for the rest of the build:**

- `Report.render_mode` defaults to **`"native"`**. Native editable charts are the primary
  deliverable (REQ-C-23).
- Phase 5 builds the remaining native builders on the **proven pattern** from Task 1.2
  (`add_chart` + `render/layout.py` manual-layout solver + raw-XML element injection via
  `chart._chartSpace`/`parse_xml`/`qn`). Task 5.4 converges `build_column_chart` to the
  `build_vertical_bar(ctx)` signature.
- **Image mode** (matplotlib → `add_picture`) remains the per-report fallback for guaranteed
  pixel-clean output and for the two types native can't do well (true funnel, combo).
- The visual-cleanliness judge becomes a **CI gate** (Phase 5 Task 5.17, Phase 9). If it later
  reveals *systematic* layout problems on real data, the response is to tune the
  `render/layout.py` solver margins / data-shaping (the design §9a step-3 render-verify loop) —
  the **structural** capability is proven, so this is tuning, not a redesign.

**The NO-GO branch was not taken.** It would have applied only if raw-OOXML layout produced
schema-invalid decks or numbers did not survive conversion — neither occurred.

## Carry-forward notes for Phase 5 (from spike reviews)

- `_value_for` raises on `None` cells (suppressed data) — add a guard when builders handle
  real survey data with missing categories.
- `build_column_chart` uses the positional spike signature — converge to `(ctx: RenderContext)`
  in Task 5.4; registry already keyed on the canonical `vertical_bar`.
- `LayoutResult.legend` is computed but not yet injected — inject the legend `c:manualLayout`
  in Phase 5.
- LibreOffice font substitution did not affect number survival but can affect the visual judge
  across runners — pin fonts (`OO_FONTDIR` / bundled fonts) before relying on the judge in CI.
- Add `--env:UserInstallation=file:///tmp/...` (isolated profile) to the soffice call before
  Phases 5/6/9 introduce concurrent conversion tests; add `Pillow` as an explicit dependency.
