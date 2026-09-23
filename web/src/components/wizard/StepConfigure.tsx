import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  AlertTriangleIcon,
  BarChart3Icon,
  GripVerticalIcon,
  ImageIcon,
  CopyIcon,
  InfoIcon,
  Loader2Icon,
  RotateCcwIcon,
  Trash2Icon,
  SparklesIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api";
import {
  decimalFieldLabel,
  decimalFields,
  showsPercentSign,
} from "@/lib/numberFormatFields";
import type { ChartSpec, ConfigField, PanelSelection, Question, Variable, GroupingOverride } from "@/lib/api";
import { useChartPreview, useChartTypes, useRegroupedQuestions, useVariables } from "@/lib/queries";
import { usePreviewStatus, useChartFacts } from "@/lib/usePreviewStatus";
import * as previewQueue from "@/lib/previewQueue";
import { useDragReorder } from "@/lib/useDragReorder";
import { slideTitle } from "@/components/wizard/slideTitle";
import QuestionDetailsDialog from "@/components/QuestionDetailsDialog";
import {
  CHART_TYPES,
  CHART_TYPE_ITEMS,
  NUMBER_FORMAT_ITEMS,
  SORT_DIRECTIONS,
  isDemographicsGrid,
  isDuplicateSlide,
  isStacked,
  isThemes,
  rendersAsBullets,
  rendersFullSlide,
  slideSubtitle,
  SLIDE_ASPECT,
  defaultRowSummaryLabel,
} from "@/lib/charts";
import { drawsTotal } from "@/lib/totalPosition";
import { legendNamesKey, legendRows, withSeriesOverride } from "@/lib/legendLabels";

// The report's grouping override, shared with the leaf preview components so a
// chart on a manually-grouped question previews the way it renders.
const GroupingCtx = createContext<GroupingOverride>({ groups: [], singles: [] });

// Which report is being previewed, and its own template choice — shared the same
// way as GroupingCtx, for the same reason: the leaf preview components call
// useChartPreview several levels down and shouldn't each take these as an
// explicit prop. reportId lets the backend's resolve_template see the report's
// own template/pin (see routes_questions.py::_preview_template); templateRef is
// in the query cache key so PICKING a new template invalidates the preview
// immediately instead of going on showing the old template's PNG.
const PreviewTemplateCtx = createContext<{ reportId?: string; templateRef?: string }>({});

// Per-chart pending flags (keyed by question_ref) from the auto-AI orchestrator.
export type AiPendingMap = Record<
  string,
  { titlePending: boolean; labelsPending: boolean; bulletsPending?: boolean }
>;

// ── Live preview ──────────────────────────────────────────────────────────
function ChartPreview({
  materialId,
  chart,
  titlePending,
  labelsPending,
  questionText,
}: {
  materialId: string;
  chart: ChartSpec;
  titlePending: boolean;
  labelsPending: boolean;
  questionText: string;
}) {
  // Debounce live edits so typing/toggling doesn't fire a render per keystroke.
  // Unchanged charts resolve INSTANTLY from the shared cache (formed once).
  const editKey = useMemo(() => JSON.stringify(chart), [chart]);
  const chartRef = useRef(chart);
  chartRef.current = chart;
  const [debounced, setDebounced] = useState(chart);
  useEffect(() => {
    const h = setTimeout(() => setDebounced(chartRef.current), 350);
    return () => clearTimeout(h);
  }, [editKey]);

  // render_title:true — the PNG is the FULL slide (title baked in), so the Design
  // preview is IDENTICAL to the Overview grid and the exported deck (WYSIWYG).
  void questionText;
  const grouping = useContext(GroupingCtx);
  const { reportId, templateRef } = useContext(PreviewTemplateCtx);
  // The queue draws this slide's headline before its picture, so there is no
  // "render now, title later" to guard against any more. `priority` promotes the
  // selected slide to the head of that one queue.
  const { data, error: qError, isFetching: loading } = useChartPreview(
    materialId,
    debounced,
    { renderTitle: false, priority: true, grouping, reportId, templateRef }
  );
  const url = data?.dataUrl;
  const error =
    qError instanceof Error ? qError.message : qError ? "Preview failed" : null;
  // Any pending state (re-rendering, or AI title / label generation) shows the single
  // "Updating…" animation over a dimmed slide — no separate per-region placeholders.
  // "Is anything still being made for this slide?" — asked of the thing doing
  // the work, rather than of a flag threaded down from the wizard that could
  // disagree with it (and, when one was stranded, did).
  const queued = usePreviewStatus(debounced.slide_id ?? "");
  // "Pending" counts as busy. A slide waiting behind fifty others is not
  // finished, and saying nothing until its turn came is what made changing the
  // template look like it had done nothing at all.
  const busyState = (s?: string) => s === "running" || s === "pending";
  const producing =
    busyState(queued.title) || busyState(queued.bullets) || busyState(queued.chart);
  const busy = loading || producing || titlePending || labelsPending;

  return (
    // Full-width preview: no padding — the border frames the slide itself. The
    // box matches the slide's aspect ratio, so the height follows the available
    // width and there's no white space around the slide. (SLIDE_ASPECT)
    <div className={`relative w-full overflow-hidden rounded-lg border bg-muted/30 ${SLIDE_ASPECT}`}>
        {url ? (
          <img
            src={url}
            alt="Chart preview"
            className={cn(
              "absolute inset-0 size-full object-contain transition duration-200",
              busy && "scale-[0.99] opacity-50 blur-[3px]"
            )}
          />
        ) : (
          !error && (
            <div className="flex size-full flex-col items-center justify-center gap-3 text-muted-foreground">
              <ImageIcon className="size-8 opacity-40" />
              <span className="text-sm">Rendering preview…</span>
            </div>
          )
        )}

        {busy && url && (
          <div className="absolute inset-0 z-20 flex items-center justify-center">
            <div className="flex items-center gap-3 rounded-full bg-background/95 px-6 py-3 text-base font-semibold text-foreground shadow-xl ring-1 ring-border backdrop-blur-sm">
              <Loader2Icon className="size-6 animate-spin text-primary" strokeWidth={2.75} />
              Updating…
            </div>
          </div>
        )}

        {error && (
          <div className="absolute inset-x-4 bottom-4 z-20 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive shadow-sm">
            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
            <span className="leading-snug">{error}</span>
          </div>
        )}
    </div>
  );
}

// ── A labelled control row ──────────────────────────────────────────────────
function Field({
  label,
  required,
  hint,
  action,
  children,
}: {
  label: string;
  required?: boolean;
  /** What this control does. Shown on hover behind an info icon beside the
   *  label, never as a paragraph under the control: a settings panel of twenty
   *  fields, each with two lines of prose under it, is a wall to scroll past
   *  rather than a form to fill in. The text is still one keystroke away for
   *  anyone who wants it. (Johan, 2026-09-07) */
  hint?: React.ReactNode;
  /** A control that belongs to the setting rather than to its value — the
   *  "Show" tick. It sits at the RIGHT END of the label row, so the row reads
   *  "what this is … whether it is drawn" and the field below it is only ever
   *  the value. (Johan, 2026-09-07) */
  action?: React.ReactNode;
  /** Optional: a setting whose whole value IS its "Show" tick has no control to
   *  put under the label, and inventing one — a sentence showing what it would
   *  look like — means writing example data into a panel every customer sees.
   *  (Johan, 2026-09-16) */
  children?: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex min-h-5 items-center justify-between gap-2">
        <Label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          {label}
          {required && <span className="ml-0.5 text-destructive">*</span>}
          {hint ? <FieldHint>{hint}</FieldHint> : null}
        </Label>
        {action}
      </div>
      {children}
    </div>
  );
}

/** The "Show" tick in a field's label row. */
function ShowToggle({
  checked,
  onChange,
  label = "Show",
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
}) {
  return (
    <label className="flex shrink-0 items-center gap-1.5 text-xs text-muted-foreground">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      {label}
    </label>
  );
}

/** The info icon beside a field's label, and the help behind it.
 *
 *  A button, not a bare icon: hover alone reaches nobody on a touch screen and
 *  nobody using a keyboard, and the tooltip primitive opens on focus and tap as
 *  well as hover once it has something focusable to hang on.
 */
function FieldHint({ children }: { children: React.ReactNode }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <button
            type="button"
            // Not a form control: inside a <label>, a plain button would still
            // forward its click to the input the label names.
            onClick={(e) => e.preventDefault()}
            aria-label="What this setting does"
            className="inline-flex text-muted-foreground/70 transition-colors hover:text-foreground focus-visible:text-foreground focus-visible:outline-none"
          />
        }
      >
        <InfoIcon className="size-3.5" />
      </TooltipTrigger>
      {/* The popup is an `inline-flex … items-center gap-1.5` row by default —
          built for a one-line label. Prose with a <code> or two in it becomes
          several flex items and lays itself out in narrow columns, so this one
          is a block, and the help is wrapped so the popup holds exactly one
          child whatever the hint is made of. */}
      <TooltipContent side="top" className="block max-w-xs">
        <span className="block text-xs font-normal leading-snug">
          {children}
        </span>
      </TooltipContent>
    </Tooltip>
  );
}

// ── Schema-driven config form ───────────────────────────────────────────────
// The per-chart config form is rendered entirely from the active chart type's
// plugin-declared schema (GET /chart-types). Adding a chart type — or a new
// option of an EXISTING widget type — needs no change here; only a brand-new
// widget type does.

interface WidgetProps {
  field: ConfigField;
  chart: ChartSpec;
  materialId: string;
  question: Question | undefined;
  variables: Variable[] | undefined;
  onChange: (patch: Partial<ChartSpec>) => void;
}

// Read/patch a config key: a first-class ChartSpec field when one exists, else
// the free-form `options` bag — so a new chart type's new option needs no
// ChartSpec change to round-trip.
function readField(chart: ChartSpec, key: string): unknown {
  if (key in chart) return (chart as unknown as Record<string, unknown>)[key];
  return chart.options?.[key];
}
// First-class ChartSpec fields that may be ABSENT on a chart loaded from an older
// saved report (added after that report was written). They must still patch the
// top-level field, not the free-form options bag.
// First-class ChartSpec fields that may be ABSENT from a chart object — either on
// a report written before the field existed, or on one makeChart just created.
// Without this, patchField sees `key in chart === false` and writes the value to
// the free-form `options` bag, where the backend never reads it: choosing
// "Top 2 sum" on a new slide was silently lost on ten of the customer's slides.
const FIRST_CLASS_KEYS = new Set([
  "percent_base",
  "show_total",
  "total_position",
  "classifying_var_2",
  "row_summary_fn",
  "row_summary_codes",
  "row_summary_pos_codes",
  "row_summary_neg_codes",
  "row_summary_label",
]);

function patchField(
  chart: ChartSpec,
  key: string,
  value: unknown
): Partial<ChartSpec> {
  if ((key in chart || FIRST_CLASS_KEYS.has(key)) && key !== "options") {
    return { [key]: value } as Partial<ChartSpec>;
  }
  return { options: { ...(chart.options ?? {}), [key]: value } };
}

function SelectWidget({ field, chart, variables, onChange }: WidgetProps) {
  const opts = field.options ?? [];
  const items = Object.fromEntries(opts.map((o) => [o.value, o.label]));
  const value = String(
    readField(chart, field.key) ?? field.default ?? opts[0]?.value ?? ""
  );
  // A banner classifier's groups come from separate columns and can overlap, so
  // it cannot be CROSSED with a second variable — only the crossed layouts
  // ("Combined panel" / "Grouped bars" / "Small multiples") are disabled here;
  // "Separate panels" does not cross them, so it stays selectable. (spec 2026-08-04)
  const bannerLocked = field.key === "xtab_layout" && usesBannerClassifier(chart, variables);
  const bannerLabel =
    (variables ?? []).find((v) => v.name === chart.classifying_var)?.label ||
    chart.classifying_var ||
    "This variable";
  const bannerReason = `${bannerLabel}'s groups come from separate columns and can overlap, so they cannot be crossed with another variable.`;
  return (
    <Field label={field.label} hint={field.help}>
      <Select
        items={items}
        value={value}
        onValueChange={(v) => onChange(patchField(chart, field.key, v))}
      >
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {opts.map((o) => {
            const disabled = bannerLocked && o.value !== "separate";
            return (
              <SelectItem
                key={o.value}
                value={o.value}
                disabled={disabled}
                title={disabled ? bannerReason : undefined}
              >
                {o.label}
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
    </Field>
  );
}

// Cross-tab percentage DIRECTION control. The engine values stay
// question/classifier/total/auto, but the labels NAME the actual variables so the
// analyst picks the grouping they want ("% within each Sukupuoli") without needing to
// know which variable is the internal base vs classifier. `question` distributes within
// each base category (→ each base group sums to 100 %); `classifier` within each
// classifier group. Variable-named labels only when a single classifier is set and the
// labels are loaded; otherwise the plugin's static labels. (spec 2026-07-10)
const PCT_DIRECTION_HINT =
  "“% within each X” means each X’s bars add up to 100 %.";

function shortVarLabel(label: string | undefined, name: string): string {
  const t = (label || "").replace(/\s+/g, " ").trim() || name;
  return t.length > 24 ? t.slice(0, 23) + "…" : t;
}

function PercentBaseWidget({ field, chart, question, variables, onChange }: WidgetProps) {
  // The percentage DIRECTION only applies to the % statistic on a classified,
  // non-stacked chart. A 100%-stacked bar is always "within each bar", so the choice
  // doesn't apply. When it doesn't apply, keep an empty grid cell (right of
  // "Statistic") so nothing else re-lays-out.
  if (
    chart.statistic !== "pct" ||
    !chart.classifying_var ||
    chart.chart_type.startsWith("stacked")
  ) {
    return <div aria-hidden />;
  }
  const byName = new Map((variables ?? []).map((v) => [v.name, v]));
  const baseVar = question ? byName.get(question.variables?.[0] ?? "") : undefined;
  const clfVar = chart.classifying_var ? byName.get(chart.classifying_var) : undefined;
  // Name the variables only for a single-classifier chart with labels loaded — a second
  // classifier makes the "classifier" side a combination, so keep static labels there.
  const useNamed =
    (variables?.length ?? 0) > 0 && !!baseVar && !!clfVar && !chart.classifying_var_2;
  // No "Automatic": it decided nothing — it resolved to the classifier
  // direction every time — while telling the author the tool had worked
  // something out about their variables. The two readings are different numbers
  // about different things, so the slide says which one it is showing.
  const opts: [string, string][] = useNamed
    ? [
        ["classifier", `% within each ${shortVarLabel(clfVar!.label, clfVar!.name)}`],
        ["question", `% within each ${shortVarLabel(baseVar!.label, baseVar!.name)}`],
        ["total", "% of the total"],
      ]
    : (field.options ?? []).map((o) => [o.value, o.label]);
  // A banner classifier's segments may overlap, so they cannot be distributed
  // within a category — drop that direction rather than offer nonsense.
  const banner = usesBannerClassifier(chart, variables);
  const shown = banner ? opts.filter(([v]) => v !== "question") : opts;
  // A report saved before the option was dropped still says "auto"; it always
  // meant this direction, so that is what the control shows for it.
  const saved = String(chart.percent_base ?? field.default ?? "classifier");
  const value = saved === "auto" ? "classifier" : saved;
  const items = Object.fromEntries(opts);
  return (
    <Field label={field.label} hint={useNamed ? PCT_DIRECTION_HINT : field.help}>
      <Select
        items={items}
        value={value}
        onValueChange={(v) => onChange({ percent_base: v } as Partial<ChartSpec>)}
      >
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {shown.map(([v, l]) => (
            <SelectItem key={v} value={v}>
              {l}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </Field>
  );
}

function SwitchWidget({ field, chart, onChange }: WidgetProps) {
  const checked = Boolean(readField(chart, field.key) ?? field.default ?? false);
  return (
    <Field label={field.label}>
      <div className="flex h-8 items-center">
        <Switch
          checked={checked}
          onCheckedChange={(c: boolean) =>
            onChange(patchField(chart, field.key, c))
          }
        />
      </div>
    </Field>
  );
}

// A "good" classifying (segmentation) variable is a low-cardinality categorical
// — gender, age group, region, experience — not a scale, free text, or a
// high-cardinality list. Keep the chart's own variable(s) selectable-by-value
// even if filtered, so an existing pick is never hidden.
function isSegmenter(v: Variable): boolean {
  // The backend ranks rather than decides (P-C-12, agreed 2026-08-24): tier 0 is
  // a background variable, tier 1 a rating item — both legitimate things to
  // split by — and tier 2 is offered only when the analyst asks to see
  // everything. Rating items used to be refused outright, which made "show this
  // by how satisfied they are" impossible.
  if (typeof v.classifier_tier === "number") return v.classifier_tier <= 1;
  if (typeof v.segmentable === "boolean") return v.segmentable;
  const n = v.n_values ?? 0;
  return v.measurement === "categorical" && n >= 2 && n <= 15;
}

/** Background variables first, then rating items, each in file order.
 *  An analyst reaches for age and region far more often than for a Likert item,
 *  so the ordering keeps the common case at the top of the list. */
function byClassifierTier(a: Variable, b: Variable): number {
  return (a.classifier_tier ?? 0) - (b.classifier_tier ?? 0);
}

/** True when the chart's primary classifier is a BANNER — a question-backed
 * classifier built from separate indicator columns, whose segments may overlap.
 * Such a classifier supports neither a second classifier nor the "within each
 * category" percentage direction. (spec 2026-08-02 §2.4, §2.5) */
function usesBannerClassifier(chart: ChartSpec, variables?: Variable[]): boolean {
  if (!chart.classifying_var) return false;
  return (variables ?? []).some(
    (v) => v.name === chart.classifying_var && v.banner === true
  );
}

function ClassifyingVarWidget({
  field,
  chart,
  materialId,
  variables,
  onChange,
}: WidgetProps) {
  const qc = useQueryClient();
  // Generic over the field key so it drives BOTH the primary classifying_var and
  // the secondary classifying_var_2 (cross-tab).
  const key = field.key as "classifying_var" | "classifying_var_2";
  // A field that vanishes teaches the author nothing — "the horizontal bar no
  // longer lets me pick a second classifying variable" was this, silently. Always
  // render it; say why when it cannot be used yet. A banner primary no longer
  // disables this row — separate mode does not cross the two variables, so
  // picking a second one against a banner primary is legal. (spec 2026-08-04)
  const noPrimary = key === "classifying_var_2" && !chart.classifying_var;
  const current = (chart[key] as string | null | undefined) ?? null;
  const other =
    key === "classifying_var_2" ? chart.classifying_var : chart.classifying_var_2 ?? null;
  const required = !!field.required;
  const missing = required && !current;
  // "Show everything" — the answer to the failure this rule replaced.
  //
  // Every reported problem was a variable that SHOULD have been a classifier and
  // was not offered, with nothing said: the packaging study's polku column,
  // derived 0/1 segment flags, analyst recodes whose names look like paradata.
  // Each was fixed by adding a heuristic, and each fix left the next file's
  // surprise in place — because whether a variable is background or measured is
  // a fact about the researcher's intent, and SPSS metadata does not record
  // intent. So nothing is unreachable now, and picking something the heuristic
  // did not offer teaches it (see onValueChange).
  const [showAll, setShowAll] = useState(false);
  const offered = (variables ?? []).filter((v) => v.name !== other);
  const suggested = offered.filter((v) => isSegmenter(v) || v.name === current);
  const rest = offered.filter((v) => !suggested.includes(v));
  const candidates = [...suggested].sort(byClassifierTier);
  const extra = showAll ? rest : [];
  const items: Record<string, string> = {
    __none__: "None",
    ...Object.fromEntries(candidates.map((v) => [v.name, v.label])),
    ...Object.fromEntries(
      extra.map((v) => [
        v.name,
        // Say why it was held back, so choosing it is an informed act rather
        // than a guess.
        v.not_offered_because ? `${v.label} — ${v.not_offered_because}` : v.label,
      ])
    ),
  };
  // A banner classifier cannot be CROSSED with a second variable (its groups come
  // from separate columns and can overlap), but it can sit beside one. Whenever the
  // pair becomes banner + second, pin the layout to Separate panels so the chart is
  // never left in a state the engine rejects — and so the author is not sent to a
  // control (Variable layout) that only appears once two classifiers exist.
  // Applies to BOTH edit directions: picking a second var against a banner primary,
  // and switching the primary to a banner var while a second is already set.
  // (spec 2026-08-04)
  const withBannerGuard = (patch: Partial<ChartSpec>): Partial<ChartSpec> => {
    const next = { ...chart, ...patch } as ChartSpec;
    if (
      next.classifying_var &&
      next.classifying_var_2 &&
      usesBannerClassifier(next, variables) &&
      (next.options?.xtab_layout ?? "auto") !== "separate"
    ) {
      return {
        ...patch,
        options: { ...(chart.options ?? {}), xtab_layout: "separate" },
      };
    }
    return patch;
  };
  const reason = noPrimary ? "Choose a classifying variable first." : undefined;
  // How many the heuristic held back. A rule nobody can inspect is a rule
  // nobody can trust, and this is the difference between "the tool is wrong"
  // and "the tool made a choice I can change".
  const hiddenCount = rest.length;
  return (
    <Field
      label={field.label}
      required={required}
      hint={field.help}
    >
      <Select
        items={items}
        value={current ?? "__none__"}
        disabled={noPrimary}
        onValueChange={(v) => {
          // Choosing something the heuristic did not offer marks it for this
          // dataset, so it appears normally for every colleague and every later
          // report on the same data. The team teaches the tool about their file
          // once, instead of a new rule being shipped per customer.
          const picked = rest.find((x) => x.name === v);
          if (picked && materialId) {
            void api.materials
              .markClassifier(materialId, picked.name, true)
              .then(() => {
                qc.invalidateQueries({ queryKey: ["variables", materialId] });
                toast.success(`"${picked.label}" is now offered as a classifying variable`);
              })
              .catch(() => {
                /* the pick still works for this chart; only the memory failed */
              });
          }
          onChange(
            withBannerGuard({ [key]: v === "__none__" ? null : v } as Partial<ChartSpec>)
          );
        }}
      >
        <SelectTrigger
          className={cn("w-full", missing && "border-destructive")}
          disabled={noPrimary}
        >
          <SelectValue placeholder="None" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="__none__">None</SelectItem>
          {candidates.map((v) => (
            <SelectItem key={v.name} value={v.name}>
              {v.label}
            </SelectItem>
          ))}
          {/* Held back by the heuristic, shown on request — each with the
              reason, so choosing one is an informed act rather than a guess. */}
          {extra.map((v) => (
            <SelectItem key={v.name} value={v.name}>
              {v.not_offered_because ? `${v.label} — ${v.not_offered_because}` : v.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {/* What the list is NOT showing, and a way to look.
          Silence was the actual defect: a variable the heuristic judged
          unsuitable looked exactly like one the file never contained, so every
          case became a support question. */}
      {hiddenCount > 0 && (
        <button
          type="button"
          className="mt-1 text-left text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          onClick={() => setShowAll((x) => !x)}
        >
          {showAll
            ? "Show only the usual variables"
            : `${hiddenCount} more variable${hiddenCount === 1 ? "" : "s"} not usually used for splitting — show them`}
        </button>
      )}
      {key === "classifying_var_2" && current && chart.classifying_var && (
        <button
          type="button"
          className="mt-1 text-left text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
          onClick={() =>
            onChange(
              withBannerGuard({
                classifying_var: current,
                classifying_var_2: chart.classifying_var,
              } as Partial<ChartSpec>)
            )
          }
        >
          ⇄ Swap — make the other variable the primary (outer) grouping
        </button>
      )}
      {/* The REASON stays in the panel: it says why the control above it is
          disabled or empty, which is not help text somebody goes looking for —
          it is the answer to "why can I not use this". The field's own help
          moved to the info icon in the label row. */}
      {reason && (
        <p className="text-xs leading-snug text-muted-foreground">{reason}</p>
      )}
    </Field>
  );
}

function SortWidget({ field, chart, question, onChange }: WidgetProps) {
  // A scale keeps its order whatever the basis says — `_single` swaps in
  // "data_order" for a partially-labelled scale, for a stacked bar split by a
  // classifier, and for a stacked bar of a rating scale, because a size sort
  // scatters a scale and leaves "Top 2" summing two bands that are no longer
  // adjacent. Offering Percentage / Mean / Count there is a control that
  // changes nothing, so those are dropped rather than shown inert.
  //
  // The two that remain are the two that WORK: survey order, and the order the
  // author dragged — a drag is an instruction, not a sort, so it wins over the
  // scale rule in the engine too. (mirrors stats/engine.py `_single`)
  const stacked = isStacked(chart.chart_type);
  const orderIsFixed =
    // an endpoint-labelled scale is drawn in scale order on every chart type…
    (question?.fixed_category_order ?? false) ||
    // …an ordinary rating scale, and a split, only where the stack would break
    (stacked && ((question?.rating_scale ?? false) || !!chart.classifying_var));
  const opts = (field.options ?? []).filter(
    (o) => !orderIsFixed || o.value === "data_order" || o.value === "manual"
  );
  const items = Object.fromEntries(opts.map((o) => [o.value, o.label]));
  // Survey order has a direction of its own: Ascending lists the entries as
  // the data has them, Descending reverses them — so a region coded 0/1 can
  // put its 1 first. Only a DRAGGED order has none: it is the order.
  const survey = chart.sort.basis === "data_order";
  const dirDisabled = chart.sort.basis === "manual";
  const dirValue = survey
    ? (chart.sort.survey_descending ? "desc" : "asc")
    : (chart.sort.descending ? "desc" : "asc");
  return (
    <>
      <Field label={field.label}>
        <Select
          items={items}
          value={chart.sort.basis}
          onValueChange={(v) =>
            onChange({
              sort: {
                ...chart.sort,
                basis: v as ChartSpec["sort"]["basis"],
                // Choosing Survey order starts where the data does.
                ...(v === "data_order" ? { survey_descending: false } : {}),
              },
            })
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {opts.map((o) => (
              <SelectItem key={o.value} value={o.value}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>

      {/* Sort direction — separate control; descending is the default for a
          value sort, ascending (the data's own order) for Survey order. */}
      <Field label="Sort direction">
        <Select
          items={Object.fromEntries(SORT_DIRECTIONS.map((s) => [s.id, s.label]))}
          value={dirValue}
          onValueChange={(v) =>
            onChange({
              sort: survey
                ? { ...chart.sort, survey_descending: v === "desc" }
                : { ...chart.sort, descending: v === "desc" },
            })
          }
          disabled={dirDisabled}
        >
          <SelectTrigger className="w-full" disabled={dirDisabled}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SORT_DIRECTIONS.map((s) => (
              <SelectItem key={s.id} value={s.id}>
                {s.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
    </>
  );
}

//: Which chart types hide a value for being too small at all. A plain bar
//: writes its values outside the bar and never hides one, so the field is not
//: offered there. The NUMBER each type uses comes from the backend
//: (`label_floor_default`) — the renderer applies it, and a second copy here
//: would be one edit away from disagreeing with it.
const HAS_LABEL_FLOOR = new Set([
  "stacked_horizontal_bar",
  "stacked_vertical_bar",
  "pie",
  "doughnut",
]);

function NumberFormatWidget({ field, chart, onChange }: WidgetProps) {
  const manual = chart.number_format.mode === "manual";
  // The catalog is fetched once and cached, so asking for it here costs nothing.
  const { data: chartTypes } = useChartTypes();
  const floorDefault = HAS_LABEL_FLOOR.has(chart.chart_type)
    ? (chartTypes?.find((t) => t.id === chart.chart_type)?.label_floor_default ?? 1)
    : undefined;
  return (
    <>
      <Field label={field.label}>
        <Select
          items={NUMBER_FORMAT_ITEMS}
          value={chart.number_format.mode}
          onValueChange={(v) =>
            onChange({
              number_format: {
                ...chart.number_format,
                mode: v as "auto" | "manual",
              },
            })
          }
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="auto">Auto</SelectItem>
            <SelectItem value="manual">Manual</SelectItem>
          </SelectContent>
        </Select>
      </Field>

      {floorDefault !== undefined && (
        <Field
          label="Hide values below"
          hint={`A slice narrower than this is not labelled at all. Above it, a number too wide for its own slice is drawn beside the chart on a line back to it, rather than left to land on its neighbour. Leave blank for the default (${floorDefault} %); 0 labels every value.`}
        >
          <div className="flex items-center gap-2">
            <Input
              type="number"
              min={0}
              max={100}
              step={0.5}
              className="w-24"
              placeholder={String(floorDefault)}
              value={chart.number_format.hide_below_pct ?? ""}
              onChange={(e) =>
                onChange({
                  number_format: {
                    ...chart.number_format,
                    hide_below_pct:
                      e.target.value === "" ? null : Number(e.target.value),
                  },
                })
              }
            />
            <span className="text-sm text-muted-foreground">%</span>
          </div>
        </Field>
      )}

      {manual && (decimalFields(chart).length > 0 || showsPercentSign(chart)) && (
        <div className="col-span-2 grid grid-cols-3 items-end gap-4 rounded-lg border bg-muted/30 p-3">
          {/* One box per measure this chart actually draws, named specifically
              only when there are two of them to tell apart. See
              lib/numberFormatFields. */}
          {decimalFields(chart).map((field) => (
            <Field
              key={field}
              label={decimalFieldLabel(field, decimalFields(chart))}
            >
              <Input
                type="number"
                min={0}
                max={4}
                value={
                  field === "pct"
                    ? chart.number_format.pct_decimals
                    : chart.number_format.mean_decimals
                }
                onChange={(e) =>
                  onChange({
                    number_format: {
                      ...chart.number_format,
                      [field === "pct" ? "pct_decimals" : "mean_decimals"]:
                        Number(e.target.value) || 0,
                    },
                  })
                }
              />
            </Field>
          ))}
          {showsPercentSign(chart) && (
            <Field label="% sign">
              <div className="flex h-8 items-center">
                <Switch
                  checked={chart.number_format.show_pct_sign}
                  onCheckedChange={(c: boolean) =>
                    onChange({
                      number_format: { ...chart.number_format, show_pct_sign: c },
                    })
                  }
                />
              </div>
            </Field>
          )}
        </div>
      )}
    </>
  );
}

function NoteWidget({ field }: WidgetProps) {
  return (
    <div className="col-span-2 rounded-lg border border-dashed bg-muted/30 px-4 py-3 text-sm text-muted-foreground">
      {field.help}
    </div>
  );
}

/** A combo's secondary variable, and — when it needs one — which of its groups.
 *
 *  A numeric or rating variable is drawn as its MEAN per category. A
 *  categorical one has no mean worth drawing, so it is drawn as the SHARE of one
 *  of its groups ("Kyllä", "Nainen"); only those variables ask for a group.
 *  Offering the numeric ones alone hid every background variable an author
 *  would put beside a question as bars. (Johan, 2026-09-17)
 *
 *  A variable that is both — an age bracket whose labels start with digits —
 *  may be drawn either way, so its group list starts with "Mean".
 */
function NumericVarWidget({ field, chart, materialId, variables, onChange }: WidgetProps) {
  const grouping = useContext(GroupingCtx);
  const saved = (readField(chart, field.key) as string | null) ?? null;
  // A categorical variable picked but no group yet. Held here rather than
  // saved: saved on its own it would be drawn as the mean of its codes, which
  // is the nonsense this picker exists to avoid.
  const [pending, setPending] = useState<string | null>(null);
  const current = pending ?? saved;
  const group = pending
    ? null
    : ((chart.options?.["combo_secondary_value"] as string | null | undefined) ?? null);
  const candidates = (variables ?? []).filter(
    (v) => v.aggregatable || v.segmentable || v.name === saved
  );
  const chosen = candidates.find((v) => v.name === current);
  // Asked of the question, as the classifier picker asks it, so the groups
  // offered are the ones the engine will find under the same names.
  const needsGroups = !!chosen && (!!chosen.segmentable || !chosen.aggregatable);
  const { data, isPending } = useQuery({
    queryKey: ["segments", materialId, chart.question_ref, current,
               JSON.stringify(grouping ?? {})],
    queryFn: () => api.segments(materialId, chart.question_ref, current!, grouping),
    enabled: !!materialId && !!current && needsGroups,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const groups = data?.segments ?? [];
  const canMean = !chosen || !!chosen.aggregatable;

  // One patch for both keys: a group belongs to the variable it was picked
  // from, and leaving it behind would name a group the new variable lacks.
  const pickVariable = (v: string | null) => {
    const name = v === "__none__" ? null : v;
    const picked = candidates.find((c) => c.name === name);
    if (picked && !picked.aggregatable) {
      setPending(name);
      return;
    }
    setPending(null);
    onChange({ options: { ...(chart.options ?? {}), [field.key]: name,
                          combo_secondary_value: null } });
  };
  const pickGroup = (g: string | null) => {
    setPending(null);
    onChange({ options: { ...(chart.options ?? {}), [field.key]: current,
                          combo_secondary_value: g === "__mean__" ? null : g } });
  };

  return (
    <>
      <Field label={field.label} hint={field.help ?? undefined}>
        <Select
          items={{
            __none__: "None",
            ...Object.fromEntries(candidates.map((v) => [v.name, v.label])),
          }}
          value={current ?? "__none__"}
          onValueChange={pickVariable}
        >
          <SelectTrigger className="w-full">
            <SelectValue placeholder="None" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__none__">None</SelectItem>
            {candidates.map((v) => (
              <SelectItem key={v.name} value={v.name}>
                {v.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      {needsGroups && (
        <Field label="Secondary group"
               hint="Drawn as the share (%) of each category's respondents in this group.">
          {isPending ? (
            <p className="text-xs text-muted-foreground">Reading the groups…</p>
          ) : (
            <Select
              items={{
                ...(canMean ? { __mean__: "Mean" } : {}),
                ...Object.fromEntries(groups.map((g) => [g, g])),
              }}
              value={group ?? (canMean ? "__mean__" : null)}
              onValueChange={pickGroup}
            >
              <SelectTrigger className="w-full">
                <SelectValue placeholder="Choose a group" />
              </SelectTrigger>
              <SelectContent>
                {canMean && <SelectItem value="__mean__">Mean</SelectItem>}
                {groups.map((g) => (
                  <SelectItem key={g} value={g}>{g}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </Field>
      )}
    </>
  );
}

/** Which two segments a scatter plots against each other.
 *
 *  Every category becomes a point: its value in the X group against its value
 *  in the Y group — how each attribute moved between two waves, or how it
 *  stands for us against a competitor. So the choice is two of the groups the
 *  classifier produced, and only the data knows what those are called.
 *
 *  Says what is missing rather than rendering two empty selects: without a
 *  classifier there are no groups, and with one group there is nothing to plot
 *  against. An empty picker with no explanation is the thing that generates
 *  support questions.
 */
function ScatterXyWidget({ chart, materialId, onChange }: WidgetProps) {
  const grouping = useContext(GroupingCtx);
  const clf = chart.classifying_var;
  const { data, isPending } = useQuery({
    // The grouping is in the key because it is in the REQUEST: regrouping
    // variables into a battery changes which segments come back, and a key that
    // ignored it served the pre-grouping list for five minutes.
    queryKey: ["segments", materialId, chart.question_ref, clf,
               JSON.stringify(grouping ?? {})],
    queryFn: () => api.segments(materialId, chart.question_ref, clf!, grouping),
    enabled: !!materialId && !!clf,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const segments = data?.segments ?? [];
  const [x, y] = chart.scatter_xy ?? [undefined, undefined];

  if (!clf) {
    return (
      <p className="text-xs text-muted-foreground">
        Choose a classifying variable first — its groups are what a scatter
        plots against each other.
      </p>
    );
  }
  if (isPending) {
    return <p className="text-xs text-muted-foreground">Reading the groups…</p>;
  }
  if (segments.length < 2) {
    return (
      <p className="text-xs text-muted-foreground">
        This variable has only one group with answers in it, so there is nothing
        to plot it against. Pick a classifying variable with at least two.
      </p>
    );
  }

  // Both must be set together: `scatter_xy` is a pair, and the renderer refuses
  // a half-configured one rather than guessing an axis.
  const set = (nx: string | undefined, ny: string | undefined) =>
    onChange({ scatter_xy: nx && ny ? [nx, ny] : null });

  return (
    <div className="flex gap-2">
      {([["X", x, (v: string | null) => set(v ?? undefined, y)],
         ["Y", y, (v: string | null) => set(x, v ?? undefined)]] as const).map(
        ([axis, value, pick]) => (
        <label key={axis} className="min-w-0 flex-1">
          <span className="mb-1 block text-xs text-muted-foreground">{axis} axis</span>
          <Select value={value ?? ""} onValueChange={pick}>
            <SelectTrigger className="w-full">
              <SelectValue placeholder="Choose a group" />
            </SelectTrigger>
            <SelectContent>
              {segments.map((s) => (
                <SelectItem key={s} value={s}>{s}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </label>
        )
      )}
    </div>
  );
}

// Dispatch a schema field to its widget. Unknown widget types are skipped so an
// older UI degrades gracefully against a newer schema.

/** Which of the classifying variable's groups this SLIDE is drawn on.
 *
 *  A battery crossed with a classifier is three dimensions and a chart holds
 *  two, so every statement becomes several bars — twenty statements by three
 *  countries is sixty bars nobody can read. Naming one group gives the whole
 *  battery seen through that group, and the next slide is the same battery
 *  through the next one: duplicate the slide, change the tick.
 *
 *  All ticked is stored as NO restriction, not as "every group listed". This is
 *  the only place that knows the full list, so it is the only place that can
 *  tell the two apart — and once the rows are narrowed the finished chart
 *  cannot: the groups left are always exactly the ones picked.
 */
function ClassifierValuesWidget({ field, chart, materialId, onChange }: WidgetProps) {
  const grouping = useContext(GroupingCtx);
  const clf = chart.classifying_var;
  const { data, isPending } = useQuery({
    // The grouping is in the key because it is in the REQUEST: regrouping
    // variables into a battery changes which segments come back, and a key that
    // ignored it served the pre-grouping list for five minutes.
    queryKey: ["segments", materialId, chart.question_ref, clf,
               JSON.stringify(grouping ?? {})],
    queryFn: () => api.segments(materialId, chart.question_ref, clf!, grouping),
    enabled: !!materialId && !!clf,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const groups = data?.segments ?? [];
  const picked = chart.classifying_values ?? [];
  // Empty means all — so an empty selection SHOWS as everything ticked, which is
  // also what the chart does.
  const on = (g: string) => picked.length === 0 || picked.includes(g);

  // Nothing to pick from without a classifying variable, and an explanation of
  // why an empty control is empty is still an empty control: the field appears
  // when choosing the variable gives it something to say. (author's call)
  if (!clf) return null;
  if (isPending) {
    return (
      <Field label={field.label}>
        <p className="text-xs text-muted-foreground">Reading the groups…</p>
      </Field>
    );
  }
  if (groups.length < 2) return null;   // nothing to choose between

  const toggle = (g: string) => {
    const now = picked.length === 0 ? groups : picked;
    const next = now.includes(g) ? now.filter((x) => x !== g) : [...now, g];
    // Every group ticked is not a subset: store "no restriction" so the slide
    // says nothing about groups and reads as the whole sample.
    const all = next.length === groups.length;
    onChange({ classifying_values: all || next.length === 0 ? [] : next });
  };

  // A chart drawn one panel per group can give the whole study a panel of its
  // own — "Total next to 25–34-vuotiaat", asked for from the field. It is not
  // one of the groups: it counts everyone, whichever groups are ticked, so it
  // is its own tick and its own setting. (2026-09-19)
  const totalPanel = PANEL_CHART_TYPES.includes(chart.chart_type);
  const totalOn = chart.show_total === "on";

  return (
    <Field label={field.label}>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {totalPanel && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={totalOn}
              onChange={() => onChange({ show_total: totalOn ? "off" : "on" })}
            />
            Total (all respondents)
          </label>
        )}
        {groups.map((g) => (
          <label key={g} className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={on(g)} onChange={() => toggle(g)} />
            {g}
          </label>
        ))}
      </div>
    </Field>
  );
}

function FieldWidget(props: WidgetProps) {
  const { field, question, chart, materialId, onChange } = props;
  switch (field.widget) {
    case "select":
      // The cross-tab direction control names the actual variables so the analyst
      // picks the grouping they want without knowing base/classifier roles.
      if (field.key === "percent_base") return <PercentBaseWidget {...props} />;
      return <SelectWidget {...props} />;
    case "switch":
      return <SwitchWidget {...props} />;
    case "variable":
      return <ClassifyingVarWidget {...props} />;
    case "numeric_variable":
      return <NumericVarWidget {...props} />;
    case "sort":
      return <SortWidget {...props} />;
    case "number_format":
      return <NumberFormatWidget {...props} />;
    case "scatter_xy":
      return <ScatterXyWidget {...props} />;
    case "classifier_values":
      return <ClassifierValuesWidget {...props} />;
    case "note":
      return <NoteWidget {...props} />;
    case "text":
      return <TextWidget {...props} />;
    case "not_answered":
      // Single categorical only — self-hides otherwise.
      if (!(question && (question.values?.length ?? 0) > 0)) return null;
      // The row-summary "sum"/"net" pickers reuse this widget type but bind to
      // their OWN ChartSpec field (row_summary_codes/pos/neg), not not_answered_codes.
      if (field.key.startsWith("row_summary_")) {
        return (
          <div className="col-span-2">
            <CodeMultiPicker field={field} chart={chart} question={question} onChange={onChange} />
          </div>
        );
      }
      return (
        <div className="col-span-2">
          <NotAnsweredPicker chart={chart} question={question} onChange={onChange} />
        </div>
      );
    case "category_labels": {
      // One place for every name on the slide: the answers, then whatever else
      // the legend shows. Each half hides itself when it has nothing to list.
      const answers = !!question && (question.category_labels?.length ?? 0) > 0;
      return (
        <div className="col-span-2 space-y-3">
          {answers && (
            <CategoryLabelEditor
              chart={chart}
              question={question}
              materialId={materialId}
              onChange={onChange}
            />
          )}
          <LegendLabelEditor
            chart={chart}
            question={question}
            materialId={materialId}
            onChange={onChange}
          />
        </div>
      );
    }
    default:
      return null;
  }
}

function ConfigForm({
  schema,
  chart,
  materialId,
  question,
  variables,
  onChange,
}: {
  schema: ConfigField[];
  chart: ChartSpec;
  materialId: string;
  question: Question | undefined;
  variables: Variable[] | undefined;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  // Two columns at the Design page's wider config width: simple fields sit
  // two-across; complex widgets (number format, not-answered, category labels)
  // already declare `col-span-2` so they span the full width.
  return (
    <div className="grid grid-cols-2 items-start gap-4">
      {schema.map((field, i) => (
        <FieldWidget
          key={`${field.key}-${i}`}
          field={field}
          chart={chart}
          materialId={materialId}
          question={question}
          variables={variables}
          onChange={onChange}
        />
      ))}
    </div>
  );
}

// ── Controls for the active chart (schema-driven) ───────────────────────────
function ChartControls({
  chart,
  materialId,
  question,
  onChange,
}: {
  chart: ChartSpec;
  materialId: string;
  question: Question | undefined;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  const { data: variables } = useVariables(materialId);
  const { data: chartTypes } = useChartTypes();

  const catalog = useMemo(
    () => new Map((chartTypes ?? []).map((c) => [c.id, c])),
    [chartTypes]
  );
  const rawSchema = catalog.get(chart.chart_type)?.config ?? [];
  const isBattery = question?.kind === "battery";
  // The engine DOES split a battery by a classifying variable: `_battery` gives one
  // bar per statement PER SEGMENT (a concept test comparing two paths on the same
  // battery), and `_battery_stacked` turns each statement into "<statement> ·
  // <segment>" bars. So `classifying_var` MUST stay in the schema for a battery —
  // do not restore a filter that hides it. (stats/engine.py `_battery` /
  // `_battery_stacked`; tests/suite/unit/stats/test_battery_crosstab.py; 2026-08-02)
  //
  // `xtab_layout` still goes. A SECOND classifier now works for a battery —
  // both battery paths cross the two variables into combo segments
  // (stats/engine.py `_crossed_masks`; tests/suite/unit/stats/
  // test_battery_two_classifiers.py) — but the LAYOUT control does not: the
  // machinery behind "separate" is `_separate_masks`, which only
  // `_single`/`_multi`/`_summary` consume. Offering it here would let somebody
  // choose separate panels and get crossed ones, which is the same lie in a
  // smaller place.
  let schema = isBattery
    ? rawSchema.filter((f) => f.key !== "xtab_layout")
    : rawSchema;
  // A multi-response question has no scale to take a "top N" of — its options are
  // unordered categories, not points on a scale, so "Top 3" would just mean
  // "whichever 3 options happen to sort last." Worse, a respondent can pick
  // several options, so the option percentages OVERLAP: on the customer's own
  // var7 slide the visible segments already sum to 465%, not 100%, so a "Sum of
  // selected" or "Net" column would double-count respondents rather than
  // summarize them. The engine reflects this: `row_summary` is only computed in
  // `_single` (stats/engine.py:832) and `_battery_stacked` (:1608) — `_multi`
  // never computes it, so picking a function here silently no-ops. Strip the
  // whole row-summary group for a multi rather than teach `_multi` to compute a
  // number that would be meaningless anyway; this must apply even to a chart
  // that already has a stored `row_summary_fn` (e.g. from before this fix, or a
  // question re-typed to multi) — a stored value stays inert, do not resurrect
  // the control to "match" it. (2026-08-07)
  const isMulti = question?.kind === "multi";
  if (isMulti) {
    schema = schema.filter(
      (f) =>
        f.key !== "row_summary_fn" &&
        f.key !== "row_summary_label" &&
        f.key !== "row_summary_codes" &&
        f.key !== "row_summary_pos_codes" &&
        f.key !== "row_summary_neg_codes"
    );
  }
  // The "Total column" control only makes sense once a classifying variable is
  // chosen — without one there is no Total to toggle. `classifying_var_2` STAYS in
  // the schema without a primary — ClassifyingVarWidget renders it disabled with a
  // stated reason, instead of the row disappearing. (percent_base stays in the
  // schema even when it doesn't apply — PercentBaseWidget renders an empty
  // placeholder so the "Statistic" row keeps its layout.) (spec 2026-08-04)
  if (!chart.classifying_var) {
    schema = schema.filter((f) => f.key !== "show_total");
  }
  // "Total position" only while a Total is actually drawn: a classifying
  // variable, no crossed second one (combos carry no Total), and "Total column"
  // resolving to shown. (2026-09-11)
  if (!drawsTotal(chart)) {
    schema = schema.filter((f) => f.key !== "total_position");
  }
  // "Show each panel's base" is gone (2026-09-17): every group's "n" is the one
  // "Group sizes" switch, wherever it is drawn. A slide saved with the old
  // setting off still hides it — the renderer reads it — but nothing offers it.
  schema = schema.filter((f) => f.key !== "show_panel_base");
  // The two-variable LAYOUT control only applies once there are two classifiers.
  if (!chart.classifying_var_2) {
    schema = schema.filter((f) => f.key !== "xtab_layout");
  }
  // Row-summary sub-fields depend on the chosen function (the whole group is only
  // present in the stacked_horizontal_bar schema, so it never shows on other types):
  // the header once a function is picked; each code picker only for its function.
  const rsFn = chart.row_summary_fn ?? "none";
  schema = schema.filter((f) => {
    if (f.key === "row_summary_label") return rsFn !== "none";
    if (f.key === "row_summary_codes") return rsFn === "sum";
    if (f.key === "row_summary_pos_codes" || f.key === "row_summary_neg_codes")
      return rsFn === "net";
    return true;
  });
  const supportsClassifying = (typeId: string) =>
    (catalog.get(typeId)?.config ?? []).some((f) => f.key === "classifying_var");

  // Switching to a chart type with no classifying variable (e.g. a single-series
  // pie) drops any stale classifying_var, so it can't silently split the data
  // into series the chart can't show.
  const supportsClassifying2 = (typeId: string) =>
    (catalog.get(typeId)?.config ?? []).some((f) => f.key === "classifying_var_2");
  const handleTypeChange = (patch: Partial<ChartSpec>) => {
    const extra: Partial<ChartSpec> = {};
    if (patch.chart_type && !supportsClassifying(patch.chart_type) && chart.classifying_var) {
      extra.classifying_var = null;
    }
    // Dropping to a chart type without a 2nd classifier clears the cross-tab.
    if (patch.chart_type && !supportsClassifying2(patch.chart_type) && chart.classifying_var_2) {
      extra.classifying_var_2 = null;
    }
    // A stale `separate` (or any other pinned layout) must not survive onto a type
    // with no second classifier — the "Variable layout" control disappears with
    // it, but the value would otherwise sit inert in options and resurface if the
    // type later regains a second classifier.
    if (
      patch.chart_type &&
      !supportsClassifying2(patch.chart_type) &&
      chart.options?.xtab_layout
    ) {
      extra.options = { ...(chart.options ?? {}), xtab_layout: undefined };
    }
    onChange({ ...patch, ...extra });
  };

  return (
    <div className="space-y-4">
      <ChartTypeField chart={chart} question={question} onChange={handleTypeChange} />
      <SlideTitleField
        chart={chart}
        materialId={materialId}
        questionText={question?.text ?? chart.question_ref}
        onChange={onChange}
      />
      <SubtitleField
        chart={chart}
        questionText={question?.text ?? chart.question_ref}
        onChange={onChange}
      />
      <AxisTitleFields chart={chart} onChange={onChange} />
      <FooterNoteField chart={chart} onChange={onChange} />
      <GroupBaseField chart={chart} onChange={onChange} />
      <ConfigForm
        schema={schema}
        chart={chart}
        materialId={materialId}
        question={question}
        variables={variables}
        onChange={onChange}
      />
    </div>
  );
}

// ── Editable slide title (headline) — editable right here in Design ──────────
function SlideTitleField({
  chart,
  questionText,
  onChange,
}: {
  chart: ChartSpec;
  materialId: string;
  questionText: string;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  return (
    <Field
      label="Slide title"
      hint="The headline shown on the slide. Leave blank to use the question text; press Enter to break it onto up to three lines. The preview updates live."
    >
      <Textarea
        value={chart.slide_title ?? ""}
        placeholder={questionText}
        rows={3}
        className="resize-y"
        onChange={(e) =>
          // Hand-typed always wins: clear slide_title_key so this title is never
          // mistaken for stale AI output and silently regenerated over.
          onChange({ slide_title: e.target.value, slide_title_key: null })
        }
      />
    </Field>
  );
}

// ── Editable axis titles (P-C-27's fourth text property) ─────────────────────
// The requirement asks that a chart's title, subtitle, value names and AXIS names
// all be editable here. The first three were; axis names had only an on/off
// toggle and no text field anywhere.
//
// These are PRESENTATION: they are in the image fingerprint, so editing one
// re-renders the slide, and deliberately not in titleDataKey, so it never spends
// an LLM call rewriting the headline.
//
// Chart families with no axes do not show the fields at all. A pie has nothing to
// name, a funnel draws with its axes switched off, and a radar's are angular —
// offering the field there means the author types a name, watches the field keep
// it, and gets a chart without it, with nothing saying the chart type was why.
const CHART_TYPES_WITH_AXES = new Set([
  "vertical_bar", "horizontal_bar", "stacked_vertical_bar", "stacked_horizontal_bar",
  "line", "scatter", "combo",
]);

function AxisTitleFields({
  chart,
  onChange,
}: {
  chart: ChartSpec;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  if (!CHART_TYPES_WITH_AXES.has(chart.chart_type)) return null;
  return (
    <div className="grid grid-cols-2 gap-3">
      <Field label="X axis title">
        <Input
          value={chart.axis_x_title ?? ""}
          onChange={(e) => onChange({ axis_x_title: e.target.value })}
        />
      </Field>
      <Field label="Y axis title">
        <Input
          value={chart.axis_y_title ?? ""}
          onChange={(e) => onChange({ axis_y_title: e.target.value })}
        />
      </Field>
    </div>
  );
}

// ── Editable subtitle (the question line shown just above the chart) ──────────
function SubtitleField({
  chart,
  questionText,
  onChange,
}: {
  chart: ChartSpec;
  questionText: string;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  // The question, and nothing else. The scale's endpoint wording ("1 = … · 5 =
  // …") used to be prefilled here to match what the renderer appended; neither
  // happens now — the subtitle is the author's line, and the scale's meaning
  // belongs in the legend, where every point can be named.
  const fallback = questionText;
  const shown = chart.elements?.subtitle !== false;
  return (
    <Field
      label="Subtitle"
      hint="The question line shown just above the chart. Defaults to the question text; edits are saved to this report only — they don’t rename the question. Clear the box to restore the default."
      /* Emptying the box means "use the question", which is the right default
         and no way to say "none" — so "none" is a tick, not a magic value in a
         text box. */
      action={
        <ShowToggle
          checked={shown}
          onChange={(v) =>
            onChange({ elements: { ...chart.elements, subtitle: v } })
          }
        />
      }
    >
      <Textarea
        value={chart.slide_description ?? fallback}
        rows={2}
        disabled={!shown}
        className="resize-y disabled:opacity-50"
        onChange={(e) => onChange({ slide_description: e.target.value || null })}
      />
    </Field>
  );
}

// ── Editable methodology footer (the N notation at the slide's bottom-left) ───
function FooterNoteField({
  chart,
  onChange,
}: {
  chart: ChartSpec;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  const shown = chart.elements?.n !== false;
  return (
    <Field
      label="Footer / N notation"
      hint={
        <>
          The methodology line at the bottom-left of the slide.{" "}
          <code>{"{n}"}</code> = the respondent count, <code>{"{stat}"}</code> ={" "}
          the statistic label — e.g. <code>{"{stat} · n = {n}"}</code> → “Osuus
          vastaajista (%) · n = 950”. Untick to draw no footer at all; a slide
          that left groups out still discloses that.
        </>
      }
      action={
        <ShowToggle
          checked={shown}
          onChange={(v) => onChange({ elements: { ...chart.elements, n: v } })}
        />
      }
    >
      <Input
        value={chart.footer_note ?? "N = {n}"}
        disabled={!shown}
        className="disabled:opacity-50"
        onChange={(e) => onChange({ footer_note: e.target.value || null })}
      />
    </Field>
  );
}

// ── Group sizes: the "(n=516)" after a group's own name ─────────────────────
function GroupBaseField({
  chart,
  onChange,
}: {
  chart: ChartSpec;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  // Only where there ARE groups to size. Without a classifying variable the
  // chart is one series for everybody, its base is the slide's own N in the
  // footer, and nothing appends "(n=…)" anywhere — so the switch would be a
  // control that changes nothing. With one, the groups are named either in the
  // legend or on the bars, and both carry the base. (Johan, 2026-09-16)
  if (!chart.classifying_var) return null;
  // Older reports have no such field; their behaviour was on.
  const shown = chart.elements?.group_base !== false;
  return (
    <Field
      label="Group sizes"
      hint={
        <>
          The <code>(n=…)</code> after a group’s own name — in the legend where
          the series are the groups, and on the bars where the bars are.
          Separate from the footer’s N, which is the whole slide’s base. Untick
          where the group sizes are stated elsewhere and repeating them is
          noise.
        </>
      }
      action={
        <ShowToggle
          checked={shown}
          onChange={(v) =>
            onChange({ elements: { ...chart.elements, group_base: v } })
          }
        />
      }
    />
  );
}

// ── "Not answered" value picker ─────────────────────────────────────────────
function NotAnsweredPicker({
  chart,
  question,
  onChange,
}: {
  chart: ChartSpec;
  question: Question;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  const detected = useMemo(
    () => (question.missing_values ?? []).map((m) => m.code),
    [question.missing_values]
  );
  // null = "use detected": fall back to the SAV-detected missing set for display.
  const usingDetected = chart.not_answered_codes === null;
  const checked = useMemo(
    () => new Set(chart.not_answered_codes ?? detected),
    [chart.not_answered_codes, detected]
  );
  const values = question.values ?? [];

  const toggle = (code: number) => {
    const next = new Set(checked);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    // Once the user edits, write the explicit list (even if it equals detected).
    onChange({ not_answered_codes: Array.from(next) });
  };

  if (values.length === 0) return null;

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          "Not answered" values
          <FieldHint>
            Choose which answers count as “Not answered”. Defaults to the values
            flagged missing in the data.
          </FieldHint>
        </Label>
        {!usingDetected && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 px-2 text-xs text-muted-foreground"
            onClick={() => onChange({ not_answered_codes: null })}
          >
            <RotateCcwIcon className="size-3" />
            Reset to detected
          </Button>
        )}
      </div>
      <div className="max-h-36 space-y-0.5 overflow-y-auto">
        {values.map((v) => (
          <label
            key={v.code}
            className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-muted/60"
          >
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={checked.has(v.code)}
              onChange={() => toggle(v.code)}
            />
            <span className="tabular-nums text-muted-foreground">
              {v.code}
            </span>
            <span className="min-w-0 flex-1 truncate">{v.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

// ── Generic text field (schema widget "text") ───────────────────────────────
// Binds to field.key. For the row-summary header the placeholder shows the
// function's default label so an empty field still previews sensibly.
function TextWidget({ field, chart, onChange }: WidgetProps) {
  const value = (chart as unknown as Record<string, unknown>)[field.key];
  const placeholder =
    field.key === "row_summary_label" ? defaultRowSummaryLabel(chart.row_summary_fn) : "";
  return (
    <Field label={field.label}>
      <Input
        value={(value as string) ?? ""}
        placeholder={placeholder}
        onChange={(e) => onChange({ [field.key]: e.target.value } as Partial<ChartSpec>)}
      />
    </Field>
  );
}

// ── Multi-select of the scale's value codes, bound to field.key ─────────────
// Used by the row-summary "Summed codes" / "Positive codes" / "Negative codes"
// pickers. Same look as NotAnsweredPicker but writes its own field (no detected
// fallback — the default is an empty selection).
function CodeMultiPicker({
  field,
  chart,
  question,
  onChange,
}: {
  field: ConfigField;
  chart: ChartSpec;
  question: Question;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  const values = question.values ?? [];
  const current =
    ((chart as unknown as Record<string, unknown>)[field.key] as number[] | undefined) ?? [];
  const checked = useMemo(() => new Set(current), [current]);
  const toggle = (code: number) => {
    const next = new Set(checked);
    if (next.has(code)) next.delete(code);
    else next.add(code);
    onChange({ [field.key]: Array.from(next) } as Partial<ChartSpec>);
  };
  if (values.length === 0) return null;
  return (
    <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
      <Label className="text-xs font-medium text-muted-foreground">{field.label}</Label>
      <div className="max-h-36 space-y-0.5 overflow-y-auto">
        {values.map((v) => (
          <label
            key={v.code}
            className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-sm hover:bg-muted/60"
          >
            <input
              type="checkbox"
              className="size-4 accent-primary"
              checked={checked.has(v.code)}
              onChange={() => toggle(v.code)}
            />
            <span className="tabular-nums text-muted-foreground">{v.code}</span>
            <span className="min-w-0 flex-1 truncate">{v.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
}

// A label-override text field with LOCAL state, committing to the report on
// blur/Enter. Typing stays local so the heavy per-keystroke re-render cascade
// (preview re-fetch, draft update) can't steal focus or reset the cursor.
function LabelOverrideInput({
  full,
  value,
  onCommit,
}: {
  full: string;
  value: string;
  onCommit: (v: string) => void;
}) {
  const [local, setLocal] = useState(value);
  const focused = useRef(false);
  // Sync external changes (e.g. "Shorten with AI" rewrites all) only when the
  // user isn't actively editing this field.
  useEffect(() => {
    if (!focused.current) setLocal(value);
  }, [value]);
  return (
    <Input
      value={local}
      placeholder={full}
      className="h-8"
      onFocus={() => {
        focused.current = true;
      }}
      onChange={(e) => setLocal(e.target.value)}
      onBlur={() => {
        focused.current = false;
        if (local !== value) onCommit(local);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") (e.target as HTMLInputElement).blur();
      }}
    />
  );
}

// ── Legend names that are not answers (groups, a combo's secondary series) ───
function LegendLabelEditor({
  chart,
  question,
  materialId,
  onChange,
}: {
  chart: ChartSpec;
  question: Question | undefined;
  materialId: string;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  const grouping = useContext(GroupingCtx);
  // Asked of the server, from the chart as computed: which names a slide draws
  // depends on its type, its split and its secondary variable, and a list the
  // editor worked out for itself would disagree with the slide sooner or later.
  const { data } = useQuery({
    queryKey: ["legend-names", materialId, legendNamesKey(chart),
               JSON.stringify(grouping ?? {})],
    queryFn: () => api.materials.legendNames(materialId, chart, grouping),
    enabled: !!materialId && !!chart.question_ref,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const rows = legendRows(data?.names ?? [], question?.category_labels ?? []);
  if (rows.length === 0) return null;
  const renames = new Map(chart.series_label_overrides ?? []);
  const setOverride = (full: string, shown: string) =>
    onChange({ series_label_overrides: withSeriesOverride(chart.series_label_overrides, full, shown) });

  return (
    <div className="space-y-1.5">
      <Label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
        Legend labels
        <FieldHint>
          The names the legend shows besides the answers — the groups of the
          classifying variable, and a combo&apos;s secondary series. Restoring
          the original name removes the rename.
        </FieldHint>
      </Label>
      <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
        {rows.map((full) => (
          <div key={full} className="flex items-center gap-1 pl-5">
            <div className="min-w-0 flex-1">
              <LabelOverrideInput
                full={full}
                value={renames.get(full) ?? full}
                onCommit={(v) => setOverride(full, v)}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Category-label editor (editable short labels + Shorten with AI) ──────────
function CategoryLabelEditor({
  chart,
  question,
  materialId,
  onChange,
}: {
  chart: ChartSpec;
  question: Question;
  materialId: string;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  const [shortening, setShortening] = useState(false);

  const overrideMap = useMemo(() => {
    const m = new Map<string, string>();
    for (const [full, short] of chart.category_label_overrides) m.set(full, short);
    return m;
  }, [chart.category_label_overrides]);

  // Write/update a single [full, short] override; empty or == full removes it.
  const setOverride = (full: string, short: string) => {
    const trimmed = short.trim();
    const pairs = chart.category_label_overrides.filter(([f]) => f !== full);
    if (trimmed && trimmed !== full) pairs.push([full, short]);
    onChange({ category_label_overrides: pairs });
  };

  // What the list SHOWS: the author's arrangement when there is one, otherwise
  // the order the data came in. Categories the stored order does not name go
  // behind the ones it does — a re-imported dataset with a new option must
  // still offer it — and names the data no longer has simply drop out. The
  // engine applies the identical rule (stats/sorting.apply_manual_order), so
  // this list is what the slide draws rather than a second opinion about it.
  const base = question.category_labels ?? [];
  const ordered = useMemo(() => {
    const wanted = chart.sort.basis === "manual" ? chart.sort.manual_order : [];
    if (!wanted.length) return base;
    const named = wanted.filter((f) => base.includes(f));
    return [...named, ...base.filter((f) => !named.includes(f))];
  }, [base, chart.sort.basis, chart.sort.manual_order]);

  // Dragging IS the sort: there is one order, and the basis says which rule
  // produced it. Anything else lets the panel claim "Percentage" while drawing
  // the arrangement somebody dragged.
  const reorder = (from: number, to: number) => {
    const next = [...ordered];
    const [moved] = next.splice(from, 1);
    next.splice(to, 0, moved);
    onChange({ sort: { ...chart.sort, basis: "manual", manual_order: next } });
  };
  const { dragIndex, overIndex, containerRef, itemProps } = useDragReorder(reorder);

  const shortenWithAI = async () => {
    setShortening(true);
    try {
      const { overrides } = await api.materials.aiShortLabels(materialId, {
        question_ref: chart.question_ref,
      });
      // Keep only meaningful shortenings (non-empty, actually shorter/different).
      const useful = overrides.filter(
        ([full, short]) => short.trim() && short.trim() !== full
      );
      if (useful.length === 0) {
        toast.warning("AI couldn't shorten the labels (service may be unavailable)");
        return;
      }
      onChange({ category_label_overrides: useful });
      toast.success(`Shortened ${useful.length} label(s) with AI`);
    } catch (e) {
      toast.error(
        `Shorten with AI failed: ${e instanceof Error ? e.message : "unknown error"}`
      );
    } finally {
      setShortening(false);
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <Label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
          Category labels
          <FieldHint>
            The label shown in the chart for each category — edit to shorten, or
            let AI shorten them all. Restoring the full label removes the
            override.
          </FieldHint>
        </Label>
        <Button
          variant="outline"
          size="sm"
          className="h-7 px-2.5 text-xs"
          disabled={shortening}
          onClick={shortenWithAI}
        >
          {shortening ? (
            <Loader2Icon className="size-3.5 animate-spin" />
          ) : (
            <SparklesIcon className="size-3.5" />
          )}
          {shortening ? "Shortening…" : "Shorten with AI"}
        </Button>
      </div>
      <div
        ref={containerRef as React.RefObject<HTMLDivElement>}
        className="max-h-64 space-y-1.5 overflow-y-auto pr-1"
      >
        {ordered.map((full, i) => (
          <div
            key={`${full}-${i}`}
            {...itemProps(i)}
            className={cn(
              "flex items-center gap-1 rounded-md",
              dragIndex === i && "opacity-40",
              dragIndex !== null &&
                overIndex === i &&
                dragIndex !== i &&
                "ring-2 ring-inset ring-primary"
            )}
          >
            <span
              className="shrink-0 cursor-grab text-muted-foreground/40 hover:text-muted-foreground"
              title="Drag to reorder — sets Sort to Manual"
            >
              <GripVerticalIcon className="size-4" />
            </span>
            <div className="min-w-0 flex-1">
              <LabelOverrideInput
                full={full}
                value={overrideMap.get(full) ?? full}
                onCommit={(v) => setOverride(full, v)}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChartTypeField({
  chart,
  question,
  onChange,
}: {
  chart: ChartSpec;
  question: Question | undefined;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  // The backend tells us which chart types are compatible with this question
  // (e.g. excludes pie/doughnut for multi-response). Gray out the rest. When we
  // have no list (question still loading), keep everything selectable.
  const compatible = useMemo(() => {
    const list = question?.compatible_chart_types;
    return list && list.length > 0 ? new Set(list) : null;
  }, [question?.compatible_chart_types]);

  return (
    <Field label="Chart type">
      <Select
        items={CHART_TYPE_ITEMS}
        value={chart.chart_type}
        onValueChange={(v) => onChange({ chart_type: (v as string) ?? "" })}
      >
        <SelectTrigger className="w-full">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {CHART_TYPES.map((t) => {
            // Always keep the currently-selected type selectable, even if an old
            // report picked an incompatible one — don't trap the user.
            const incompatible =
              compatible !== null &&
              !compatible.has(t.id) &&
              t.id !== chart.chart_type;
            return (
              <SelectItem key={t.id} value={t.id} disabled={incompatible}>
                {t.label}
              </SelectItem>
            );
          })}
        </SelectContent>
      </Select>
    </Field>
  );
}

// ── Special-slide preview (full PNG; no title overlay / label region) ────────
function SpecialPreview({
  materialId,
  chart,
  bulletsPending,
}: {
  materialId: string;
  chart: ChartSpec;
  bulletsPending: boolean;
}) {
  // The whole slide (heading + bullets) is baked server-side → render the full
  // PNG (renderTitle:true) and show it plainly.
  const grouping = useContext(GroupingCtx);
  const { reportId, templateRef } = useContext(PreviewTemplateCtx);
  const { data, error: qError, isFetching: loading } = useChartPreview(
    materialId,
    chart,
    { renderTitle: false, priority: true, grouping, reportId, templateRef }
  );
  const url = data?.dataUrl;
  const error =
    qError instanceof Error ? qError.message : qError ? "Preview failed" : null;
  // Re-rendering OR bullet (re)generation → the single "Updating…" animation over a
  // dimmed slide, instead of a separate region placeholder.
  const busy = loading || bulletsPending;
  return (
    // Full-width, no padding — the border frames the slide; height follows the
    // slide's aspect ratio. (SLIDE_ASPECT)
    <div className={`relative w-full overflow-hidden rounded-lg border bg-muted/30 ${SLIDE_ASPECT}`}>
        {url ? (
          <img
            src={url}
            alt="Slide preview"
            className={cn(
              "absolute inset-0 size-full object-contain transition duration-200",
              busy && "scale-[0.99] opacity-50 blur-[3px]"
            )}
          />
        ) : (
          !error && (
            <div className="flex size-full flex-col items-center justify-center gap-3 text-muted-foreground">
              <ImageIcon className="size-8 opacity-40" />
              <span className="text-sm">Rendering preview…</span>
            </div>
          )
        )}
        {busy && url && (
          <div className="absolute inset-0 z-20 flex items-center justify-center">
            <div className="flex items-center gap-3 rounded-full bg-background/95 px-6 py-3 text-base font-semibold text-foreground shadow-xl ring-1 ring-border backdrop-blur-sm">
              <Loader2Icon className="size-6 animate-spin text-primary" strokeWidth={2.75} />
              Updating…
            </div>
          </div>
        )}
        {error && (
          <div className="absolute inset-x-4 bottom-4 z-20 flex items-start gap-2 rounded-lg border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive shadow-sm">
            <AlertCircleIcon className="mt-0.5 size-4 shrink-0" />
            <span className="leading-snug">{error}</span>
          </div>
        )}
    </div>
  );
}

// ── Special-slide controls: editable heading + bullets + Regenerate ──────────
// Present stored bullets as editable Markdown: ensure every line shows a "*"
// marker (legacy AI bullets are plain), preserving any existing indent/marker so
// nesting round-trips. The renderer parses the same "*"/indent convention.
function bulletsToMarkdown(bullets: string[]): string {
  return bullets
    .map((b) => {
      const m = /^(\s*)([-*+]\s+)?(.*)$/.exec(b);
      const indent = m?.[1] ?? "";
      const marker = m?.[2] ?? "* ";
      const rest = m?.[3] ?? b;
      return rest.trim() ? `${indent}${marker}${rest}` : "";
    })
    .filter((l) => l !== "")
    .join("\n");
}

function SpecialSlideControls({
  chart,
  pending,
  onChange,
  onRegenerate,
}: {
  chart: ChartSpec;
  pending: boolean;
  onChange: (patch: Partial<ChartSpec>) => void;
  onRegenerate: () => void;
}) {
  const bullets = bulletsToMarkdown(
    (chart.options?.bullets as string[] | undefined) ?? []
  );
  const [draft, setDraft] = useState(bullets);
  const focused = useRef(false);
  // Resync when the generated bullets land (or when switching slides) — but NOT
  // while the user is actively editing, so an incoming (re)generation never
  // clobbers unsaved edits mid-type.
  useEffect(() => {
    if (!focused.current) setDraft(bullets);
  }, [bullets]);

  const commit = () => {
    focused.current = false;
    // Preserve leading whitespace (nesting) and the "*" marker; only trailing
    // spaces and blank lines are dropped. The renderer parses "*"/indent per line.
    const next = draft
      .split("\n")
      .map((l) => l.replace(/\s+$/, ""))
      .filter((l) => l.trim().length > 0);
    onChange({ options: { ...(chart.options ?? {}), bullets: next } });
  };

  return (
    <div className="space-y-4">
      <Field label="Heading">
        <LabelOverrideInput
          full="Slide heading"
          value={chart.slide_title ?? ""}
          onCommit={(v) => onChange({ slide_title: v || null })}
        />
      </Field>
      <Field
        label="Bullets"
        hint="Markdown: one bullet per line starting with *. Indent two spaces to nest."
      >
        <textarea
          className="min-h-72 w-full resize-y rounded-md border bg-background px-3 py-2 font-mono text-sm leading-relaxed shadow-sm focus:ring-2 focus:ring-primary/30 focus:outline-none"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          placeholder={
            pending
              ? "Generating…"
              : "* First point\n* Second point\n  * A nested detail"
          }
        />
      </Field>
      {/* An Empty slide has no generated content to regenerate — it is written by
          hand, so the button would do nothing but spend a call. */}
      {chart.chart_type !== "special_blank" && (
        <Button variant="outline" size="sm" disabled={pending} onClick={onRegenerate}>
          {pending ? (
            <Loader2Icon className="size-4 animate-spin" />
          ) : (
            <SparklesIcon className="size-4" />
          )}
          Regenerate
        </Button>
      )}
    </div>
  );
}

// ── Main Configure step ─────────────────────────────────────────────────────
// There is no deck-prefetch component here any more. Warming every slide was a
// second queue in all but name: it had its own debounce, its own ordering and
// its own idea of when a title was still coming, none of which agreed with the
// render gate's. The wizard enqueues the whole deck on the ONE queue instead,
// and scrolling or selecting a slide promotes it.

/** Chart types that draw ONE panel per classifier group — enough to know
 *  whether to ASK the server what it would draw. How many fit, and which
 *  groups are dropped, come back in the answer: `render/panels.py` decides
 *  that, and a second copy of the rule here could disagree with the slide. */
const PANEL_CHART_TYPES = ["pie", "doughnut", "funnel"];

export type SlideProblem = { id: string; title: string; detail: string };

/** What is wrong with this slide, in the author's terms.
 *
 *  English, like the rest of the editor. The Finnish strings this warning talks
 *  ABOUT — "Ei mahtunut sivulle" and friends — are the DECK's, printed on the
 *  slide for the client who reads it. Two audiences, two languages; do not
 *  follow the footer's lead here.
 */
/** The panel selection for one chart, or undefined while it is unknown.
 *
 *  Keyed by the three things that change the answer. Disabled unless the chart
 *  actually draws panels, so an ordinary bar chart costs no request — this runs
 *  once per slide in the list, and the list can be long.
 */
/** What this slide's picture could not say for itself.
 *
 *  Both of these used to be invisible to the author. The blank slide printed
 *  "No data to show" across the chart area — English text on a slide that goes
 *  out with the deck — and a chart too dense to label simply came out with no
 *  numbers on it and no reason given. The slide says nothing now; this is where
 *  the author is told. (Johan, 2026-09-16)
 */
export function renderProblems(facts: previewQueue.ChartFacts): SlideProblem[] {
  const out: SlideProblem[] = [];
  if (facts.empty) {
    out.push({
      id: "no-data",
      title: "Nothing to chart on this slide",
      detail:
        "Every value on this slide is missing or zero, so its picture is blank. " +
        "Usually the question has no answers under the filters this slide uses, " +
        "or the variable carries no value labels to chart. Pick another " +
        "question, widen the groups, or take the slide out — it goes into the " +
        "deck as an empty chart area otherwise.",
    });
  }
  if (facts.unlabelled) {
    out.push({
      id: "unlabelled",
      title: `${facts.unlabelled} categories, too many to label`,
      detail:
        `Each bar is under 5pt tall in this template's chart area, and a number ` +
        `printed there would overlap the bars either side of it — so the ` +
        `percentages were left off and the reader has only the axis. This is ` +
        `about the ROOM, not the question: the same chart carries its numbers ` +
        `in a taller chart area. Sort the slide and keep the largest few ` +
        `categories, or give the chart area more height in the template.`,
    });
  }
  return out;
}

function producerProblems(chart: ChartSpec | undefined): SlideProblem[] {
  const failures = previewQueue.failuresOf(chart?.slide_id ?? "");
  const say: Record<string, { title: string; detail: string }> = {
    title: {
      title: "The AI headline could not be written",
      detail:
        "This slide shows its question text instead, which is what every slide " +
        "showed before AI headlines existed. Nothing else about the slide is " +
        "affected. Editing the slide, or reopening the report, tries again.",
    },
    bullets: {
      title: "The theme bullets could not be generated",
      detail:
        "The open-ended answers could not be summarised into themes. The slide " +
        "is otherwise complete; you can type bullets yourself, or try again by " +
        "reopening the report.",
    },
    chart: {
      title: "The slide could not be rendered",
      detail:
        "The picture for this slide failed to draw. The deck cannot include it " +
        "until it does — changing anything on the slide will try again.",
    },
  };
  return failures.map((f) => {
    const copy = say[f.id];
    const why = f.error instanceof Error ? f.error.message : "";
    return {
      id: `producer-${f.id}`,
      title: copy.title,
      detail: why ? `${copy.detail}\n\nThe service said: ${why}` : copy.detail,
    };
  });
}

function usePanelSelection(
  materialId: string,
  chart: ChartSpec | undefined,
  grouping: GroupingOverride
) {
  // A CLASSIFIER is what makes this worth asking, not the chart type. Thin
  // groups are dropped by `series_values`, which every builder shares, so a bar
  // chart split six ways on a small study loses its groups exactly as a pie
  // does — and used to do it with no warning anywhere, because this asked only
  // for the panel types. A slide with no classifier still costs no request.
  // (Johan, 2026-09-16)
  const applies = !!chart && !!chart.classifying_var;
  return useQuery({
    // The selection is in the key: pick three of five groups and the warning
    // about the other two has to go, rather than sit there describing the chart
    // this slide no longer is.
    queryKey: ["panels", materialId, chart?.question_ref, chart?.classifying_var,
               (chart?.classifying_values ?? []).join("|"),
               chart?.chart_type, chart?.show_total ?? "auto",
               JSON.stringify(grouping ?? {})],
    queryFn: () =>
      api.panels(materialId, chart!.question_ref, chart!.classifying_var!, grouping,
                 chart!.classifying_values, chart!.chart_type, chart!.show_total ?? "auto"),
    enabled: applies && !!materialId,
    // The answer changes only when the data or the classifier does, and a
    // warning is not worth re-fetching on every focus.
    staleTime: 5 * 60_000,
    retry: false,
  });
}

export function slideProblems(
  chart: ChartSpec | undefined,
  panels: PanelSelection | undefined
): SlideProblem[] {
  if (!chart || !chart.classifying_var || !panels || !panels.split) return [];

  const out: SlideProblem[] = [];
  // Two reasons, two entries. Merging them would tell an author that four
  // groups "did not fit" when some of them could not have been charted at any
  // size — which is a different problem with a different answer.
  // Capping is panel-only: those chart types draw one panel per group and stop
  // at three. A bar chart draws every group it keeps, so telling its author that
  // groups "did not fit" would be false. Thin groups and a dropped split are
  // real on every chart type. (Johan, 2026-09-16)
  if (panels.capped.length && PANEL_CHART_TYPES.includes(chart.chart_type)) {
    out.push({
      id: "too-many-groups",
      title: `${panels.capped.length} group${panels.capped.length === 1 ? "" : "s"} left off this slide`,
      detail:
        `A slide holds ${panels.max_panels} charts. Drawn: ${panels.drawn.join(", ")}. ` +
        `Left out: ${panels.capped.join(", ")} — the largest groups are kept. ` +
        `The slide itself says nothing about them, so this is the only warning.`,
    });
  }
  if (panels.thin.length) {
    // Drawn, with each group's size beside its name on the slide. What the
    // author needs to know is that some percentages rest on very few people.
    // (2026-09-17 — these groups used to be left out, silently.)
    const named = panels.thin
      .map((g) => (panels.sizes?.[g] !== undefined ? `${g} (n=${panels.sizes[g]})` : g))
      .join(", ");
    out.push({
      id: "thin-groups",
      title: `${panels.thin.length} small group${panels.thin.length === 1 ? "" : "s"}`,
      detail:
        `Fewer than 10 respondents: ${named}. They are drawn, with their size ` +
        `shown on the slide, but their percentages rest on very few people — ` +
        `one answer moves them a lot. Read them with caution, or split by a ` +
        `variable with fewer, larger groups.`,
    });
  }
  if (panels.degraded) {
    out.push({
      id: "grouping-dropped",
      title: "The split could not be drawn",
      detail:
        `No group of this variable has any respondents on this slide, so it ` +
        `falls back to one chart of the whole sample rather than a blank space.`,
    });
  }
  // Which groups the slide was NARROWED to.
  //
  // Stated by the server, not inferred here. This used to compare the author's
  // ticked `classifying_values` against `drawn + thin + capped` — and those can
  // never disagree, because the endpoint computes on data already narrowed to
  // those same values, so the warning was dead in the one case it existed for.
  // Where it did fire it was worse than silent: a slide carrying group names
  // from a classifier the author had since changed got a confident "this slide
  // counts Design 1, Design 3 and nobody else" while it was the whole sample
  // split by sex. `narrowed_to` is what the engine actually applied.
  // (Johan, 2026-09-17)
  // Not when the slide also draws the Total: that panel IS the whole study,
  // so the slide says so itself. (2026-09-19)
  if (panels.narrowed_to?.length && !panels.drawn.includes("Total")) {
    const n = panels.narrowed_to.length;
    out.push({
      id: "narrowed-to-groups",
      title: `Drawn on ${n} group${n === 1 ? "" : "s"} only`,
      detail:
        `This slide counts ${panels.narrowed_to.join(", ")} and nobody else, ` +
        `and its N says so without naming them. A reader who is not told reads ` +
        `it as the whole study. Tick the rest under "Groups on this slide", or ` +
        `say which groups it covers in the slide title.`,
    });
  }
  return out;
}

/** The warning triangle on a row in the slide list.
 *
 *  Its own component so each row can ask about its own slide: the answer
 *  depends on the chart's classifier and the data, and only the server can give
 *  it. Renders nothing at all when there is nothing wrong, so the list stays
 *  quiet — a marker on every row would be no marker.
 *
 *  Matches the marker on the active slide's preview, deliberately: an author
 *  scrolling the list should be able to tell WHICH slides need attention
 *  without opening each one, which was the gap — the warning existed but only
 *  on the slide you were already looking at.
 */
function SlideWarning({
  materialId,
  chart,
  grouping,
  className,
}: {
  materialId: string;
  chart: ChartSpec;
  grouping: GroupingOverride;
  className?: string;
}) {
  const { data: panels } = usePanelSelection(materialId, chart, grouping);
  // Subscribed, so the marker appears when the picture lands rather than
  // whenever this row happens to render next — which, for a slide nobody has
  // touched, is never.
  const facts = useChartFacts(chart.slide_id ?? "");
  const problems = [...slideProblems(chart, panels), ...producerProblems(chart),
                    ...renderProblems(facts)];
  if (!problems.length) return null;
  return (
    <AlertTriangleIcon
      className={cn("size-3.5 shrink-0 text-amber-600 dark:text-amber-500", className)}
      aria-label={problems[0].title}
    >
      <title>{problems[0].title}</title>
    </AlertTriangleIcon>
  );
}

function StepConfigureInner({
  materialId,
  charts,
  grouping,
  aiPending,
  active,
  setActive,
  onCopyChart,
  onRemoveChart,
  onReorder,
  onUpdateChart,
  onRegenerateSpecial,
}: {
  materialId: string;
  charts: ChartSpec[];
  grouping: GroupingOverride;
  aiPending?: AiPendingMap;
  // The active slide (slide_id) is owned by ReportWizard so the Preview grid can
  // select a slide and jump here to edit it.
  active: string | null;
  setActive: (ref: string | null) => void;
  /** Duplicate the slide at this index. The copy lands directly below it and
   *  carries its whole configuration; the caller returns the new slide_id so
   *  it can be selected. */
  onCopyChart: (index: number) => string | null;
  /** Take this slide out of the deck. Offered on duplicates only — see
   *  `isDuplicateSlide`. */
  onRemoveChart: (index: number) => void;
  // Drag-reorder the report's slides in the left list (affects this report only).
  onReorder: (from: number, to: number) => void;
  onUpdateChart: (index: number, patch: Partial<ChartSpec>) => void;
  // Called with every chart's slide_id when Design opens so AI slide titles are
  // generated automatically in the background (batched, like the thumbnails).
  // Regenerate a special (non-chart) slide's AI content. Adding/removing/reordering
  // slides lives in the Select step now — Design only edits slide CONTENT.
  onRegenerateSpecial?: (chart: ChartSpec) => void;
  // Not read here — only by the wrapper below, which puts them in
  // PreviewTemplateCtx for the leaf preview components. Typed on this props
  // object anyway so `Parameters<typeof StepConfigureInner>[0]` (the wrapper's
  // own prop type) includes them.
  reportId?: string;
  templateRef?: string;
}) {
  const { data: questions, isError } = useRegroupedQuestions(materialId, grouping);
  const [editQid, setEditQid] = useState<string | null>(null);
  const [problemsOpen, setProblemsOpen] = useState(false);
  const activeRowRef = useRef<HTMLDivElement>(null);
  // Drag-reorder the slide list.
  const { dragIndex, overIndex, containerRef, itemProps } = useDragReorder(onReorder);
  // Scroll the active row into view when the selection changes (← / → or a jump
  // back from the Preview grid) so the highlighted slide is always visible.
  useEffect(() => {
    activeRowRef.current?.scrollIntoView({ block: "nearest" });
  }, [active]);

  // ↑ / ↓ (and ← / →) step to the previous / next slide instead of scrolling —
  // ignored while typing in a field. The active row auto-scrolls into view, so the
  // list never needs manual scrolling.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const prev = e.key === "ArrowUp" || e.key === "ArrowLeft";
      const next = e.key === "ArrowDown" || e.key === "ArrowRight";
      if (!prev && !next) return;
      const el = document.activeElement as HTMLElement | null;
      if (
        el &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.tagName === "SELECT" ||
          el.isContentEditable)
      )
        return;
      // Handle the key here (stop the page/list from scrolling) even at the ends.
      e.preventDefault();
      const cur = Math.max(0, charts.findIndex((c) => c.slide_id === active));
      const target = Math.max(
        0,
        Math.min(charts.length - 1, prev ? cur - 1 : cur + 1)
      );
      if (target !== cur && charts[target]) {
        setActive(charts[target].slide_id ?? null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [active, charts, setActive]);

  const questionMap = useMemo(() => {
    const m = new Map<string, Question>();
    (questions ?? []).forEach((q) => m.set(q.qid, q));
    return m;
  }, [questions]);

  // Auto-generate AI slide titles for every chart once Design is open (batched,
  // Titles are not requested from here any more. The preview queue owns them,
  // along with the bullets and the picture, and decides for itself what a slide
  // still needs by comparing fingerprints — so a step no longer has to notice
  // that a classifying variable changed and go asking.

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-24 text-center">
        <AlertCircleIcon className="mb-3 size-8 text-muted-foreground/50" />
        <p className="text-sm font-medium">Couldn't load this material's questions</p>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">
          It may have been removed. Re-upload the data in the Data tab.
        </p>
      </div>
    );
  }

  if (charts.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-24 text-center">
        <BarChart3Icon className="mb-3 size-8 text-muted-foreground/50" />
        <p className="text-sm font-medium">No slides yet</p>
        <p className="mt-1 max-w-xs text-sm text-muted-foreground">
          Go back to <span className="font-medium">Select</span> to add questions
          or a special slide. Design is where you shape each slide's content.
        </p>
      </div>
    );
  }

  // Resolved by slide_id, not question_ref: a deck may hold TWO slides for one
  // question — the total-level result and the same result split by another
  // variable — and matching on the question made every edit land on the first.
  const activeIndex = charts.findIndex((c) => c.slide_id === active);
  const activeChart = activeIndex >= 0 ? charts[activeIndex] : charts[0];
  // What this slide will NOT show. A pure read of the active chart and the
  // material's variables; declared here because both are only in scope now.
  // Both kinds: what the slide will not SHOW (too many groups for one slide),
  // and what could not be MADE for it (a generation that failed). They belong in
  // the same button because they are the same question to an author looking at a
  // slide that is not what they expected.
  // Subscribed, so a failure appearing while the author is looking at the slide
  // lights the button then — not on the next unrelated re-render.
  const activeStatus = usePreviewStatus(activeChart?.slide_id ?? "");
  void activeStatus;
  const { data: activePanels } = usePanelSelection(materialId, activeChart, grouping);
  const activeFacts = useChartFacts(activeChart?.slide_id ?? "");
  const activeProblems = [
    ...slideProblems(activeChart, activePanels),
    ...producerProblems(activeChart),
    ...renderProblems(activeFacts),
  ];
  const activeSpecial = activeChart ? rendersFullSlide(activeChart) : false;
  const activeBullets = activeChart ? rendersAsBullets(activeChart) : false;
  // A "themes" chart is an open-ended question rendered as bullets — unlike a true
  // special slide it HAS an alternative chart type (word cloud), so it keeps a
  // chart-type picker AND the bullet editor.
  const activeThemes = activeChart ? isThemes(activeChart) : false;
  const activeGrid = activeChart ? isDemographicsGrid(activeChart) : false;
  const activeBulletsPending =
    aiPending?.[activeChart?.slide_id ?? ""]?.bulletsPending ?? false;

  // Update the active chart; when the type switches TO themes with no bullets yet,
  // kick off theme-bullet generation so the slide isn't empty (a plain updateChart
  // only patches the type — nothing would generate the bullets otherwise).
  const handleChange = (patch: Partial<ChartSpec>) => {
    if (!activeChart) return;
    onUpdateChart(activeIndex, patch);
    const hasBullets = !!(activeChart.options?.bullets as string[] | undefined)?.length;
    if (patch.chart_type === "themes" && !hasBullets) {
      onRegenerateSpecial?.({ ...activeChart, ...patch });
    }
  };

  return (
    <div className="space-y-4">
      {/* Background: warm every slide's preview so the deck (and the Preview grid)
          are ready without clicking each slide (renders nothing). */}

      {/* Top: slide list (left) + preview (right), EQUAL HEIGHT. The list is an
          absolutely-positioned scroll area so it never grows the row — the PREVIEW
          sets the row height and the list scrolls inside it to match exactly.
          Navigation only: add / remove / reorder live in the Select step. */}
      <div className="grid grid-cols-[300px_minmax(0,1fr)] items-stretch gap-4">
        <div className="relative min-h-[16rem]">
          <div
            ref={containerRef as React.RefObject<HTMLDivElement>}
            className="absolute inset-0 space-y-1.5 overflow-y-auto pr-1"
          >
            {charts.map((c, i) => {
              const isActive = c.slide_id === active;
              return (
                <div
                  key={`${c.question_ref}-${i}`}
                  {...itemProps(i)}
                  ref={isActive ? activeRowRef : undefined}
                  className={cn(
                    "flex items-center gap-1 rounded-md transition-colors",
                    isActive ? "bg-primary/10" : "hover:bg-muted/50",
                    dragIndex === i && "opacity-40",
                    // Inset ring so the drop indicator is never clipped by the
                    // scroll container's (horizontal) overflow.
                    dragIndex !== null &&
                      overIndex === i &&
                      dragIndex !== i &&
                      "ring-2 ring-inset ring-primary"
                  )}
                >
                  <span
                    className="shrink-0 cursor-grab pl-1 text-muted-foreground/40 hover:text-muted-foreground"
                    title="Drag to reorder — affects this report only"
                  >
                    <GripVerticalIcon className="size-4" />
                  </span>
                  <button
                    onClick={() => setActive(c.slide_id ?? null)}
                    className="flex min-w-0 flex-1 items-center gap-2 py-2 pr-2 text-left outline-none focus:outline-none focus-visible:outline-none focus-visible:ring-0"
                  >
                    <span className="w-5 shrink-0 text-right text-xs tabular-nums text-muted-foreground">
                      {i + 1}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="line-clamp-1 text-sm">
                        {slideTitle(c, questionMap)}
                      </span>
                      <span className="mt-0.5 block text-xs text-muted-foreground">
                        {slideSubtitle(c, questionMap)}
                      </span>
                    </span>
                    {/* Top right, and `self-start` is what puts it there: the
                        row centres its children, so without it the triangle
                        would float beside the middle of a two-line title. Out
                        of the title's own line so a long question keeps the
                        full width to clamp into. */}
                    <SlideWarning
                      materialId={materialId}
                      chart={c}
                      grouping={grouping}
                      className="mt-0.5 self-start"
                    />
                  </button>
                </div>
              );
            })}
          </div>
        </div>

        {activeChart && (
          <div className="relative">
            {activeSpecial ? (
              <SpecialPreview
                key={activeChart.question_ref}
                materialId={materialId}
                chart={activeChart}
                bulletsPending={activeBulletsPending}
              />
            ) : (
              <ChartPreview
                key={activeChart.question_ref}
                materialId={materialId}
                chart={activeChart}
                titlePending={
                  aiPending?.[activeChart.slide_id ?? ""]?.titlePending ?? false
                }
                labelsPending={
                  aiPending?.[activeChart.slide_id ?? ""]?.labelsPending ?? false
                }
                questionText={
                  questionMap.get(activeChart.question_ref)?.text ??
                  activeChart.question_ref
                }
              />
            )}
            {/* ONE column, top-right of the picture, in source order.
                Each of these used to carry its own `absolute top-…`, recomputed
                against which of its neighbours happened to be showing — and the
                warning sat in a second column beside them because there was no
                slot left. A flex column makes the order the code's order and
                the spacing one number. (Johan, 2026-09-16) */}
            <div className="absolute right-2 top-2 z-20 flex flex-col gap-2">
            {/* What this slide will NOT show. FIRST, and never moves: it is the
                one button that reports a problem, so it must be where the eye
                lands whatever else is on the slide. */}
            {!activeSpecial && activeProblems.length > 0 && (
              <button
                type="button"
                title={activeProblems[0].title}
                aria-label={activeProblems[0].title}
                onClick={() => setProblemsOpen(true)}
                className="flex size-8 items-center justify-center rounded-md bg-destructive/10 text-destructive shadow-sm ring-1 ring-destructive/30 backdrop-blur-sm transition-colors hover:bg-destructive/20"
              >
                <AlertTriangleIcon className="size-4" />
              </button>
            )}
            {/* Question details — chart slides only (special slides are edited inline). */}
            {!activeSpecial && (
              <button
                type="button"
                title="View question details"
                onClick={() => setEditQid(activeChart.question_ref)}
                className="flex size-8 items-center justify-center rounded-md bg-background/85 text-muted-foreground shadow-sm ring-1 ring-border backdrop-blur-sm transition-colors hover:text-foreground"
              >
                <InfoIcon className="size-4" />
              </button>
            )}
            {/* Copy this slide. Here rather than in Select because what is
                worth copying is the CONFIGURATION — the chart type, the split,
                the sort, the colours — and this is the step where that exists.
                Under the (i), on the picture, because it acts on the slide you
                are looking at.

                Special slides copy too: a conclusions page is worth splitting
                in two by hand, and the copy is independent of the original's
                group so regenerating one does not take the other. */}
            <button
                type="button"
                title="Copy this slide"
                onClick={() => {
                  const id = onCopyChart(activeIndex);
                  // Select the copy: otherwise the only visible effect is a new
                  // thumbnail below, and the whole point is to change something
                  // about it — the chart type, the split — straight away.
                  if (id) setActive(id);
                }}
                className="flex size-8 items-center justify-center rounded-md bg-background/85 text-muted-foreground shadow-sm ring-1 ring-border backdrop-blur-sm transition-colors hover:text-foreground"
              >
                <CopyIcon className="size-4" />
              </button>
            {/* Draw this slide again.
                Always offered, not only when something is marked wrong — the
                fault it exists for shows nothing wrong at all: a slide that is
                blank while the queue believes it is finished. A button that
                appeared only next to a recorded failure would be missing in
                exactly that case. It also lifts the automatic bounds, which
                have to exist so a slide that cannot be drawn stops occupying
                the render host, and which are the only thing in the way once
                the reason has been dealt with. */}
            {activeChart?.slide_id && (
              <button
                type="button"
                title="Draw this slide again"
                aria-label="Draw this slide again"
                onClick={() => previewQueue.redraw(activeChart.slide_id!)}
                className="flex size-8 items-center justify-center rounded-md bg-background/85 text-muted-foreground shadow-sm ring-1 ring-border backdrop-blur-sm transition-colors hover:text-foreground"
              >
                <RotateCcwIcon className="size-4" />
              </button>
            )}
            {/* Remove this slide — a DUPLICATE only. It is the one slide Select
                cannot remove: a chart slide's copy shares its question with the
                original, so unticking that question hides both, and a special
                slide never had a row there. Everything else is removed by
                unticking its question, which hides it where it stands and gives
                it back untouched. */}
            {activeChart && isDuplicateSlide(activeChart) && (
              <button
                type="button"
                title="Remove this duplicate"
                aria-label="Remove this duplicate"
                onClick={() => {
                  const gone = activeIndex;
                  // Land on a neighbour, or the pane keeps showing a slide that
                  // is no longer in the deck.
                  const next = charts[gone + 1] ?? charts[gone - 1];
                  onRemoveChart(gone);
                  setActive(next?.slide_id ?? null);
                }}
                className="flex size-8 items-center justify-center rounded-md bg-background/85 text-muted-foreground shadow-sm ring-1 ring-border backdrop-blur-sm transition-colors hover:text-destructive"
              >
                <Trash2Icon className="size-4" />
              </button>
            )}
            </div>
          </div>
        )}
      </div>

      {/* Configuration — full width below the list + preview. */}
      {activeChart && (
        <div className="rounded-xl border bg-card p-4">
          {activeSpecial ? (
            activeGrid ? (
              <p className="text-sm text-muted-foreground">
                A demographics overview — the charts are chosen automatically from the
                respondent (age, gender, geography…) questions. Remove or reorder this
                slide in the Select step.
              </p>
            ) : activeThemes ? (
              // Open-ended themes: keep the chart-type picker (themes ↔ word cloud)
              // AND the bullet editor + regenerate.
              <div className="space-y-4">
                <ChartTypeField
                  chart={activeChart}
                  question={questionMap.get(activeChart.question_ref)}
                  onChange={handleChange}
                />
                <SpecialSlideControls
                  chart={activeChart}
                  pending={activeBulletsPending}
                  onChange={(patch) => onUpdateChart(activeIndex, patch)}
                  onRegenerate={() => onRegenerateSpecial?.(activeChart)}
                />
              </div>
            ) : activeBullets ? (
              <SpecialSlideControls
                chart={activeChart}
                pending={activeBulletsPending}
                onChange={(patch) => onUpdateChart(activeIndex, patch)}
                onRegenerate={() => onRegenerateSpecial?.(activeChart)}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                This slide has no options — remove it in the Select step.
              </p>
            )
          ) : (
            <ChartControls
              chart={activeChart}
              materialId={materialId}
              question={questionMap.get(activeChart.question_ref)}
              onChange={handleChange}
            />
          )}
        </div>
      )}

      <Dialog open={problemsOpen} onOpenChange={setProblemsOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-destructive">
              <AlertTriangleIcon className="size-5 shrink-0" />
              {/* Two different things land in this dialog: content the slide
                  leaves OUT because it does not fit, and content that could not
                  be MADE. "Won't show everything" is right for the first and
                  simply wrong for the second — a slide whose headline failed
                  shows everything it has. */}
              {activeProblems.some((p) => p.id.startsWith("producer-"))
                ? "Something on this slide could not be generated"
                : "This slide won't show everything"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            {activeProblems.map((p) => (
              <div key={p.id} className="space-y-1">
                <p className="text-sm font-medium">{p.title}</p>
                <p className="text-sm leading-relaxed text-muted-foreground">{p.detail}</p>
              </div>
            ))}
            {/* Offered here too: this dialog is where an author arrives having
                just read that something could not be made, and "try it again"
                is the next thing they want. */}
            {activeProblems.some((p) => p.id.startsWith("producer-")) && activeChart?.slide_id && (
              <Button
                variant="outline"
                onClick={() => {
                  previewQueue.redraw(activeChart.slide_id!);
                  setProblemsOpen(false);
                }}
              >
                <RotateCcwIcon className="size-4" />
                Draw this slide again
              </Button>
            )}
          </div>
        </DialogContent>
      </Dialog>

      <QuestionDetailsDialog
        materialId={materialId}
        qid={editQid}
        readOnly
        grouping={grouping}
        onOpenChange={(open) => {
          if (!open) setEditQid(null);
        }}
      />
    </div>
  );
}

// Provide the report's grouping — and which report/template it's previewing —
// to the leaf preview components (via context) so they don't need any of it
// prop-drilled through the whole Design tree.
export default function StepConfigure(
  props: Parameters<typeof StepConfigureInner>[0]
) {
  return (
    <GroupingCtx.Provider value={props.grouping}>
      <PreviewTemplateCtx.Provider
        value={{ reportId: props.reportId, templateRef: props.templateRef }}
      >
        <StepConfigureInner {...props} />
      </PreviewTemplateCtx.Provider>
    </GroupingCtx.Provider>
  );
}
