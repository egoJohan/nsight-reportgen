# Cross-tab percentage direction — clear manual control — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Make the Design "Percentages of" control name the actual variables so an analyst can manually pick "each gender sums to 100 %" without knowing base/classifier roles or relying on `auto`.

**Architecture:** Frontend-only relabelling of the `percent_base` widget (dynamic labels from the chart's base + classifier variables); engine directions and stored values unchanged. Optional secondary: `auto` tie-break refinement in `resolve_percent_base`.

**Spec:** `docs/superpowers/specs/2026-07-10-crosstab-percent-direction-manual-design.md`
**Repro:** `case-134 / rep-209`, `tests/suite/unit/stats/test_percent_direction_ticket.py`

## Global Constraints
- `percent_base` values stay `{auto, classifier, question, total}`; only LABELS change.
- `question` label ↔ base variable; `classifier` label ↔ classifying variable.
- Fall back to today's static labels when variable labels are unavailable.
- Control stays hidden when `chart.classifying_var` is unset (existing behaviour).

---

### Task 1: Dynamic, variable-named `percent_base` labels

**Files:**
- Modify: `web/src/components/wizard/StepConfigure.tsx` (FieldWidget dispatch + new `PercentBaseWidget`)
- Test: Playwright check (scratchpad) on `case-134 / rep-209`

**Interfaces:**
- Consumes `WidgetProps` (`field`, `chart`, `question`, `variables`, `onChange`).
- Produces `PercentBaseWidget` rendering the four options with dynamic labels.

- [ ] **Step 1: Add the widget.** In `StepConfigure.tsx`, add:
```tsx
function PercentBaseWidget(props: WidgetProps) {
  const { field, chart, question, variables, onChange } = props;
  const byName = new Map((variables ?? []).map((v) => [v.name, v.label || v.name]));
  const baseLabel =
    (question && byName.get(question.variables?.[0] ?? "")) ??
    (question?.text ? question.text.slice(0, 28) : "this question");
  const clfLabel = chart.classifying_var
    ? byName.get(chart.classifying_var) ?? "the segment"
    : "the segment";
  // Only relabel when we actually have the variable names; else use static labels.
  const dynamic =
    variables && variables.length > 0
      ? ([
          ["question", `% within each ${baseLabel}`],
          ["classifier", `% within each ${clfLabel}`],
          ["total", "% of the total"],
          ["auto", "Automatic (recommended)"],
        ] as const)
      : (field.options ?? []).map((o) => [o.value, o.label] as const);
  const value = String(chart.percent_base ?? field.default ?? "auto");
  const items = Object.fromEntries(dynamic.map(([v, l]) => [v, l]));
  return (
    <Field label={field.label} hint={field.help}>
      <Select items={items} value={value}
        onValueChange={(v) => onChange({ percent_base: v } as Partial<ChartSpec>)}>
        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>
          {dynamic.map(([v, l]) => (
            <SelectItem key={v} value={v}>{l}</SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}
```

- [ ] **Step 2: Dispatch it.** In `FieldWidget`, before the generic `select` case:
```tsx
    case "select":
      if (field.key === "percent_base") return <PercentBaseWidget {...props} />;
      return <SelectWidget {...props} />;
```

- [ ] **Step 3: Typecheck + build.** `cd web && npx tsc -b` (expect `TSC=0`), `npm run build`.

- [ ] **Step 4: Verify (Playwright, fresh browser).** Open `http://localhost:5173/cases/case-134?report=rep-209`, Design, select slide 1 (the gender×segment chart). Assert the "Percentages of" options include `% within each` + the gender variable label and `% within each` + the segment label. Select the gender option and confirm the preview shows each gender's bars summing to 100 %.

- [ ] **Step 5: Commit.** `feat(web): name the variables in the "Percentages of" control`

---

### Task 2 (OPTIONAL, secondary): `auto` tie-break prefers the segmenter denominator

**Files:**
- Modify: `src/reportbuilder/stats/percent_base.py` (`resolve_percent_base` final comparison)
- Test: `tests/suite/unit/stats/test_percent_base_resolve.py`

**Interfaces:** unchanged signature `resolve_percent_base(question, spec, model) -> str`.

- [ ] **Step 1: Failing test.** Build a cross-tab where base and classifier BOTH score 2, but one is a demographic (score would be 3 if the regex matched) — assert current code returns `"classifier"` (documents the tie fallback), then after the fix returns `"question"` when the base is the demographic side. Add a case mirroring the existing resolve tests' fixture.

- [ ] **Step 2: Implement.** Change the final line so a tie resolves toward the stronger *segmenter role* (demographic/segment as denominator) rather than the blanket legacy `"classifier"`; keep the strict-outrank path as-is. Keep the change minimal and commented.

- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/suite/unit/stats/test_percent_base_resolve.py tests/suite/unit/stats/test_engine_percent_base_auto.py tests/suite/unit/stats/test_percent_direction_ticket.py -q` — all green.

- [ ] **Step 4: Update memory.** Refresh `crosstab-percent-direction` memo with the tie-break rule.

- [ ] **Step 5: Commit.** `fix(stats): auto percent-direction tie-break favours the segmenter denominator`

---

## Self-Review
- **Spec coverage:** manual relabel (Task 1) + optional auto tie-break (Task 2) both covered; repro test already exists as the regression anchor.
- **Type consistency:** `percent_base` value strings and the `question↔base`, `classifier↔classifier` label mapping are consistent across spec, widget, and tests.
- **Scope:** frontend labelling is self-contained and unblocks the customer alone; Task 2 is explicitly optional and independently testable.
