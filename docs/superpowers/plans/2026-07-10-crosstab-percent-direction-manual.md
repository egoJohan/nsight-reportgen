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

- [ ] **Step 1: Add the widget.** In `StepConfigure.tsx`, add. Dynamic, variable-named
  labels ONLY for a single-classifier chart with variable labels loaded; otherwise the
  static labels. `auto` is listed first (it stays the default); a single field hint
  explains the "sum to 100 %" meaning.
```tsx
const HINT = "'% within each X' means each X's bars add up to 100 %.";
function shortLabel(s: string | undefined, name: string): string {
  const t = (s || "").replace(/\s+/g, " ").trim() || name;
  return t.length > 24 ? t.slice(0, 23) + "…" : t;
}
function PercentBaseWidget(props: WidgetProps) {
  const { field, chart, question, variables, onChange } = props;
  const byVar = new Map((variables ?? []).map((v) => [v.name, v]));
  const baseVar = question ? byVar.get(question.variables?.[0] ?? "") : undefined;
  const clfVar = chart.classifying_var ? byVar.get(chart.classifying_var) : undefined;
  // Variable-named labels need: labels loaded, base + classifier resolved, and NO 2nd
  // classifier (its "classifier" side is a combination — naming one would be wrong).
  const useNamed =
    (variables?.length ?? 0) > 0 && baseVar && clfVar && !chart.classifying_var_2;
  const opts: readonly (readonly [string, string])[] = useNamed
    ? [
        ["auto", "Automatic"],
        ["question", `% within each ${shortLabel(baseVar!.label, baseVar!.name)}`],
        ["classifier", `% within each ${shortLabel(clfVar!.label, clfVar!.name)}`],
        ["total", "% of the total"],
      ]
    : (field.options ?? []).map((o) => [o.value, o.label] as const);
  const value = String(chart.percent_base ?? field.default ?? "auto");
  const items = Object.fromEntries(opts.map(([v, l]) => [v, l]));
  return (
    <Field label={field.label} hint={useNamed ? HINT : field.help}>
      <Select items={items} value={value}
        onValueChange={(v) => onChange({ percent_base: v } as Partial<ChartSpec>)}>
        <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
        <SelectContent>
          {opts.map(([v, l]) => (
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

### Task 2 (OPTIONAL, CONTINGENT on Step 0): fix `auto` only if a demographic was mis-detected

Do this ONLY if Step 0 shows the customer's failing chart uses `percent_base=="auto"` and
its two variables **tie** because a demographic wasn't matched by `_DEMOGRAPHIC_RE`. On a
genuine tie the resolver has no signal to prefer a side, so the fix is to improve DETECTION
(make the demographic score 3), NOT to flip the global tie default (which would silently
change every existing tie chart). If Step 0 shows an explicit/legacy `"classifier"`, skip
Task 2 entirely — Task 1 covers it.

**Files:**
- Modify: `src/reportbuilder/stats/percent_base.py` (`_DEMOGRAPHIC_RE` / `segmenter_score`)
- Test: `tests/suite/unit/stats/test_percent_base_resolve.py`

- [ ] **Step 1: Failing test.** For the specific variable Step 0 found, assert
`segmenter_score(var, text) == 3` and that a gender×segment chart with that variable resolves
to `"question"`. (Fails today because the label/text slips past the regex.)

- [ ] **Step 2: Implement.** Extend `_DEMOGRAPHIC_RE` (or the label/text feeding it) so that
variable is recognised as demographic; leave the strict-outrank comparison untouched.

- [ ] **Step 3: Run** `.venv/bin/python -m pytest tests/suite/unit/stats/test_percent_base_resolve.py tests/suite/unit/stats/test_engine_percent_base_auto.py tests/suite/unit/stats/test_percent_direction_ticket.py -q` — all green (no collateral direction changes).

- [ ] **Step 4: Update memory.** Refresh the `crosstab-percent-direction` memo.

- [ ] **Step 5: Commit.** `fix(stats): detect <var> as a demographic so auto percent-direction resolves correctly`

---

## Self-Review
- **Spec coverage:** manual relabel (Task 1) + optional auto tie-break (Task 2) both covered; repro test already exists as the regression anchor.
- **Type consistency:** `percent_base` value strings and the `question↔base`, `classifier↔classifier` label mapping are consistent across spec, widget, and tests.
- **Scope:** frontend labelling is self-contained and unblocks the customer alone; Task 2 is explicitly optional and independently testable.
