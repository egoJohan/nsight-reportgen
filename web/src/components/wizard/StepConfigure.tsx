import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircleIcon,
  AlertTriangleIcon,
  BarChart3Icon,
  GripVerticalIcon,
  ImageIcon,
  InfoIcon,
  Loader2Icon,
  RotateCcwIcon,
  SparklesIcon,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
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
import type { ChartSpec, ConfigField, PanelSelection, Question, Variable, GroupingOverride } from "@/lib/api";
import { useChartPreview, useChartTypes, useRegroupedQuestions, useVariables } from "@/lib/queries";
import { usePreviewStatus } from "@/lib/usePreviewStatus";
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
  isStacked,
  isThemes,
  rendersAsBullets,
  rendersFullSlide,
  slideSubtitle,
  SLIDE_ASPECT,
  defaultRowSummaryLabel,
} from "@/lib/charts";

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
  children,
}: {
  label: string;
  required?: boolean;
  // Accepted for call-site compatibility but no longer rendered — the orange
  // per-field "tips" were removed from the config section.
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-medium text-muted-foreground">
        {label}
        {required && <span className="ml-1 text-destructive">*</span>}
      </Label>
      {children}
    </div>
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
  // ("Automatic" / "Grouped bars" / "Small multiples") are disabled here;
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
  const opts: [string, string][] = useNamed
    ? [
        ["auto", "Automatic"],
        ["question", `% within each ${shortVarLabel(baseVar!.label, baseVar!.name)}`],
        ["classifier", `% within each ${shortVarLabel(clfVar!.label, clfVar!.name)}`],
        ["total", "% of the total"],
      ]
    : (field.options ?? []).map((o) => [o.value, o.label]);
  // A banner classifier's segments may overlap, so they cannot be distributed
  // within a category — drop that direction rather than offer nonsense.
  const banner = usesBannerClassifier(chart, variables);
  const shown = banner ? opts.filter(([v]) => v !== "question") : opts;
  const value = String(chart.percent_base ?? field.default ?? "auto");
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
  // control (Two-variable layout) that only appears once two classifiers exist.
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
      hint={reason ?? (missing ? "This chart needs a dimension to split by" : undefined)}
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
      {(reason ?? field.help) && (
        <p className="text-xs leading-snug text-muted-foreground">{reason ?? field.help}</p>
      )}
    </Field>
  );
}

function SortWidget({ field, chart, onChange }: WidgetProps) {
  const opts = field.options ?? [];
  const items = Object.fromEntries(opts.map((o) => [o.value, o.label]));
  const dirDisabled = chart.sort.basis === "data_order";
  return (
    <>
      <Field label={field.label}>
        <Select
          items={items}
          value={chart.sort.basis}
          onValueChange={(v) =>
            onChange({
              sort: { ...chart.sort, basis: v as ChartSpec["sort"]["basis"] },
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

      {/* Sort direction — separate control; descending is the default. Not
          applicable to "Data order" (keeps the source order as-is). */}
      <Field label="Sort direction">
        <Select
          items={Object.fromEntries(SORT_DIRECTIONS.map((s) => [s.id, s.label]))}
          value={chart.sort.descending ? "desc" : "asc"}
          onValueChange={(v) =>
            onChange({ sort: { ...chart.sort, descending: v === "desc" } })
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

function NumberFormatWidget({ field, chart, onChange }: WidgetProps) {
  const manual = chart.number_format.mode === "manual";
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

      {manual && (
        <div className="col-span-2 grid grid-cols-3 items-end gap-4 rounded-lg border bg-muted/30 p-3">
          <Field label="% decimals">
            <Input
              type="number"
              min={0}
              max={4}
              value={chart.number_format.pct_decimals}
              onChange={(e) =>
                onChange({
                  number_format: {
                    ...chart.number_format,
                    pct_decimals: Number(e.target.value) || 0,
                  },
                })
              }
            />
          </Field>
          <Field label="Mean decimals">
            <Input
              type="number"
              min={0}
              max={4}
              value={chart.number_format.mean_decimals}
              onChange={(e) =>
                onChange({
                  number_format: {
                    ...chart.number_format,
                    mean_decimals: Number(e.target.value) || 0,
                  },
                })
              }
            />
          </Field>
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

// Picker for a compatible numeric/rating secondary variable (combo line). Only
// aggregatable variables are offered, guaranteeing a meaningful mean per category.
function NumericVarWidget({ field, chart, variables, onChange }: WidgetProps) {
  const current = (readField(chart, field.key) as string | null) ?? null;
  const candidates = (variables ?? []).filter(
    (v) => v.aggregatable || v.name === current
  );
  return (
    <Field label={field.label} hint={field.help ?? undefined}>
      <Select
        items={{
          __none__: "None",
          ...Object.fromEntries(candidates.map((v) => [v.name, v.label])),
        }}
        value={current ?? "__none__"}
        onValueChange={(v) =>
          onChange(patchField(chart, field.key, v === "__none__" ? null : v))
        }
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
  );
}

// Dispatch a schema field to its widget. Unknown widget types are skipped so an
// older UI degrades gracefully against a newer schema.
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
    case "category_labels":
      if (!(question && (question.category_labels?.length ?? 0) > 0)) return null;
      return (
        <div className="col-span-2">
          <CategoryLabelEditor
            chart={chart}
            question={question}
            materialId={materialId}
            onChange={onChange}
          />
        </div>
      );
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
  // A SECOND classifier and `xtab_layout` are a different story: both battery paths
  // resolve segments via `_classifier_masks(spec, ...)` called with the PRIMARY
  // classifier only — `classifying_var_2` and `options.xtab_layout` (the machinery
  // behind `_separate_masks`, which only `_single`/`_multi`/`_summary` consume) are
  // never read for a battery. Leaving them selectable would let the author configure
  // a two-classifier / separate-panels battery that silently renders as an ordinary
  // one-classifier split — a lie about what's on screen — so both stay filtered out.
  let schema = isBattery
    ? rawSchema.filter(
        (f) => f.key !== "classifying_var_2" && f.key !== "xtab_layout"
      )
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
    // with no second classifier — the "Two-variable layout" control disappears with
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
        scaleGloss={question?.scale_gloss ?? ""}
        onChange={onChange}
      />
      <AxisTitleFields chart={chart} onChange={onChange} />
      <FooterNoteField chart={chart} onChange={onChange} />
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
    <Field label="Slide title">
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
      <p className="text-xs text-muted-foreground">
        The headline shown on the slide. Leave blank to use the question text; press
        Enter to break it onto up to three lines. The preview updates live.
      </p>
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
  scaleGloss,
  onChange,
}: {
  chart: ChartSpec;
  questionText: string;
  scaleGloss: string;
  onChange: (patch: Partial<ChartSpec>) => void;
}) {
  // A stacked bar shows the scale as bare numbers, so the renderer appends the endpoint
  // gloss ("1 = … · 5 = …") to the DEFAULT subtitle. Prefill it here so the box holds the
  // exact line that renders — a battery's gloss is taken from its first member's scale
  // and usually needs rewording once several questions are merged into one battery.
  const gloss = isStacked(chart.chart_type) ? scaleGloss : "";
  const fallback = gloss ? `${questionText}   ${gloss}` : questionText;
  return (
    <Field label="Subtitle">
      <Textarea
        value={chart.slide_description ?? fallback}
        rows={2}
        className="resize-y"
        onChange={(e) => onChange({ slide_description: e.target.value || null })}
      />
      <p className="text-xs text-muted-foreground">
        The question line shown just above the chart. Defaults to the question text
        {gloss ? " plus the scale legend" : ""}; edits are saved to this report only — they
        don’t rename the question. Clear the box to restore the default.
      </p>
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
  return (
    <Field label="Footer / N notation">
      <Input
        value={chart.footer_note ?? "N = {n}"}
        onChange={(e) => onChange({ footer_note: e.target.value || null })}
      />
      <p className="text-xs text-muted-foreground">
        The methodology line at the bottom-left of the slide. <code>{"{n}"}</code> = the
        respondent count, <code>{"{stat}"}</code> = the statistic label — e.g.{" "}
        <code>{"{stat} · n = {n}"}</code> → “Osuus vastaajista (%) · n = 950”.
      </p>
    </Field>
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
    <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs font-medium text-muted-foreground">
          "Not answered" values
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
      <p className="text-xs text-muted-foreground">
        Choose which answers count as "Not answered". Defaults to the values
        flagged missing in the data.
      </p>
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
    <div className="space-y-2 rounded-lg border bg-muted/30 p-3">
      <div className="flex items-center justify-between gap-2">
        <Label className="text-xs font-medium text-muted-foreground">
          Category labels
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
      <div className="max-h-64 space-y-1.5 overflow-y-auto pr-1">
        {(question.category_labels ?? []).map((full, i) => (
          <LabelOverrideInput
            key={`${full}-${i}`}
            full={full}
            value={overrideMap.get(full) ?? full}
            onCommit={(v) => setOverride(full, v)}
          />
        ))}
      </div>
      <p className="text-xs text-muted-foreground">
        The label shown in the chart for each category — edit to shorten, or let AI shorten
        them all. Restoring the full label removes the override.
      </p>
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

type SlideProblem = { id: string; title: string; detail: string };

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
  const applies =
    !!chart && PANEL_CHART_TYPES.includes(chart.chart_type) && !!chart.classifying_var;
  return useQuery({
    queryKey: ["panels", materialId, chart?.question_ref, chart?.classifying_var],
    queryFn: () =>
      api.panels(materialId, chart!.question_ref, chart!.classifying_var!, grouping),
    enabled: applies && !!materialId,
    // The answer changes only when the data or the classifier does, and a
    // warning is not worth re-fetching on every focus.
    staleTime: 5 * 60_000,
    retry: false,
  });
}

function slideProblems(
  chart: ChartSpec | undefined,
  panels: PanelSelection | undefined
): SlideProblem[] {
  if (!chart || !PANEL_CHART_TYPES.includes(chart.chart_type)) return [];
  if (!chart.classifying_var || !panels || !panels.split) return [];

  const out: SlideProblem[] = [];
  // Two reasons, two entries. Merging them would tell an author that four
  // groups "did not fit" when some of them could not have been charted at any
  // size — which is a different problem with a different answer.
  if (panels.capped.length) {
    out.push({
      id: "too-many-groups",
      title: `${panels.capped.length} group${panels.capped.length === 1 ? "" : "s"} left off this slide`,
      detail:
        `A slide holds ${panels.max_panels} charts. Drawn: ${panels.drawn.join(", ")}. ` +
        `Left out: ${panels.capped.join(", ")} — the largest groups are kept. ` +
        `The slide's footer names them too, so the omission travels with the deck.`,
    });
  }
  if (panels.thin.length) {
    out.push({
      id: "thin-groups",
      title: `${panels.thin.length} group${panels.thin.length === 1 ? "" : "s"} too small to report`,
      detail:
        `Too few respondents to chart: ${panels.thin.join(", ")}. ` +
        `Their percentages would be noise, so they are left out whatever else ` +
        `fits. The slide's footer names them separately from anything that ` +
        `merely ran out of room.`,
    });
  }
  if (panels.degraded) {
    out.push({
      id: "grouping-dropped",
      title: "The split could not be drawn",
      detail:
        `Every group is too small to report, so the slide falls back to one ` +
        `chart of the whole sample rather than a blank space. Split by a ` +
        `variable with fewer, larger groups.`,
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
  const problems = [...slideProblems(chart, panels), ...producerProblems(chart)];
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
  const activeProblems = [
    ...slideProblems(activeChart, activePanels),
    ...producerProblems(activeChart),
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
            {/* Question details — chart slides only (special slides are edited inline). */}
            {!activeSpecial && (
              <button
                type="button"
                title="View question details"
                onClick={() => setEditQid(activeChart.question_ref)}
                className="absolute right-2 top-2 z-20 flex size-8 items-center justify-center rounded-md bg-background/85 text-muted-foreground shadow-sm ring-1 ring-border backdrop-blur-sm transition-colors hover:text-foreground"
              >
                <InfoIcon className="size-4" />
              </button>
            )}
            {/* What this slide will NOT show. Sits beside the (i) rather than in
                the config panel: it is about the RENDERED slide, so it belongs on
                the picture. Only appears when there is something to say. */}
            {!activeSpecial && activeProblems.length > 0 && (
              <button
                type="button"
                title={activeProblems[0].title}
                aria-label={activeProblems[0].title}
                onClick={() => setProblemsOpen(true)}
                className="absolute right-12 top-2 z-20 flex size-8 items-center justify-center rounded-md bg-destructive/10 text-destructive shadow-sm ring-1 ring-destructive/30 backdrop-blur-sm transition-colors hover:bg-destructive/20"
              >
                <AlertTriangleIcon className="size-4" />
              </button>
            )}
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
