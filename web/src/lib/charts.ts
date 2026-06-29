import type {
  ChartElements,
  ChartSpec,
  NumberFormat,
  SortSpec,
} from "./api";

// ---- Chart types ----
export interface ChartTypeOption {
  id: string;
  label: string;
}

export const CHART_TYPES: ChartTypeOption[] = [
  { id: "vertical_bar", label: "Vertical Bar" },
  { id: "horizontal_bar", label: "Horizontal Bar" },
  { id: "stacked_vertical_bar", label: "Stacked Vertical Bar" },
  { id: "stacked_horizontal_bar", label: "Stacked Horizontal Bar" },
  { id: "line", label: "Line Chart" },
  { id: "pie", label: "Pie Chart" },
  { id: "doughnut", label: "Doughnut Chart" },
  { id: "radar", label: "Radar Chart" },
  { id: "scatter", label: "Scatter Plot" },
  { id: "funnel", label: "Funnel Chart" },
  { id: "wordcloud", label: "Word Cloud" },
];

export const STACKED = new Set<string>([
  "stacked_vertical_bar",
  "stacked_horizontal_bar",
]);

export const SCATTER = "scatter";

export function isStacked(chartType: string): boolean {
  return STACKED.has(chartType);
}

/** A word cloud renders from computed word frequencies; the usual statistic/
 * sort/classifying/label controls don't apply and no AI label-shortening runs. */
export function isWordcloud(chartType: string): boolean {
  return chartType === "wordcloud";
}

// ---- Special (non-chart) slide types ----
// These ride inside the charts list as ChartSpecs with question_ref="" and
// options.bullets; they render as text/bullet slides (Overview/Conclusion/
// Demographics), not data charts.
export const SPECIAL_SLIDE_LABELS: Record<string, string> = {
  special_overview: "Overview",
  special_conclusion: "Conclusion",
  special_demographics: "Demographics",
};

export function isSpecialSlide(chart: { chart_type: string }): boolean {
  return chart.chart_type in SPECIAL_SLIDE_LABELS;
}

export function chartTypeLabel(id: string): string {
  return (
    CHART_TYPES.find((c) => c.id === id)?.label ??
    SPECIAL_SLIDE_LABELS[id] ??
    id
  );
}

/** base-ui Select renders the raw value unless given an items map; these resolve labels. */
export const CHART_TYPE_ITEMS: Record<string, string> = Object.fromEntries(
  CHART_TYPES.map((t) => [t.id, t.label])
);
export const NUMBER_FORMAT_ITEMS: Record<string, string> = {
  auto: "Auto",
  manual: "Manual",
};

// ---- Statistic options ----
export interface StatisticOption {
  id: ChartSpec["statistic"];
  label: string;
}

export const STATISTICS: StatisticOption[] = [
  { id: "pct", label: "Percentage" },
  { id: "count", label: "Count" },
  { id: "mean", label: "Mean" },
  { id: "median", label: "Median" },
  { id: "sum", label: "Sum" },
];

export const STATISTIC_ITEMS: Record<string, string> = Object.fromEntries(
  STATISTICS.map((s) => [s.id, s.label])
);

// ---- Sort options (compact subset mapped to sort.basis) ----
export interface SortOption {
  id: SortSpec["basis"];
  label: string;
}

export const SORT_OPTIONS: SortOption[] = [
  { id: "pct", label: "Percentage" },
  { id: "data_order", label: "Data order" },
  { id: "mean", label: "Mean" },
  { id: "count", label: "Count" },
];

export const SORT_ITEMS: Record<string, string> = Object.fromEntries(
  SORT_OPTIONS.map((s) => [s.id, s.label])
);

// ---- Sort direction (separate from the sort basis; descending is the default) ----
export const SORT_DIRECTIONS: { id: "desc" | "asc"; label: string }[] = [
  { id: "desc", label: "Descending" },
  { id: "asc", label: "Ascending" },
];

export const SORT_DIRECTION_ITEMS: Record<string, string> = Object.fromEntries(
  SORT_DIRECTIONS.map((s) => [s.id, s.label])
);

// ---- Defaults ----
export const DEFAULT_NUMBER_FORMAT: NumberFormat = {
  mode: "auto",
  pct_decimals: 0,
  mean_decimals: 1,
  count_round_up: false,
  show_pct_sign: true,
};

export const DEFAULT_ELEMENTS: ChartElements = {
  title: true,
  legend: true,
  n: true,
  axis_names: true,
  filter_var: true,
  data_labels: true,
};

export const DEFAULT_SORT: SortSpec = {
  basis: "pct",
  topbox_codes: [],
  descending: true,
};

/**
 * Build a fresh ChartSpec for a question with sensible defaults.
 * template_slot is assigned by position later via normalizeSlots().
 */
export function makeChart(
  questionRef: string,
  suggestedChartType: string
): ChartSpec {
  return {
    question_ref: questionRef,
    chart_type: suggestedChartType || "vertical_bar",
    statistic: "pct",
    classifying_var: null,
    number_format: { ...DEFAULT_NUMBER_FORMAT },
    sort: { ...DEFAULT_SORT, topbox_codes: [] },
    template_slot: "s1",
    elements: { ...DEFAULT_ELEMENTS },
    scatter_xy: null,
    show_not_answered: false,
    // Hide 0% rows by default — the user's expectation.
    show_empty_categories: false,
    // null = use SAV-detected missing set until the user edits the picker.
    not_answered_codes: null,
    category_label_overrides: [],
    slide_title: null,
    slide_description: null,
  };
}

/**
 * Build a fresh special (non-chart) slide spec. Heading goes in slide_title,
 * bullet content in options.bullets. Carries all serde-required ChartSpec
 * fields so the backend report_from_json accepts it like any chart.
 */
// A unique id per special slide. The backend identifies special slides by
// chart_type (not question_ref), so a non-empty ref is safe — and it's required
// so that per-slide state (preview cache, AI-pending flags, updateChartByRef)
// never collides when a report holds more than one special slide.
function specialRef(type: string): string {
  const rand =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `sp_${type}_${rand}`;
}

export function makeSpecialSlide(
  type: keyof typeof SPECIAL_SLIDE_LABELS | string,
  opts?: { slide_title?: string; bullets?: string[] }
): ChartSpec {
  return {
    question_ref: specialRef(type),
    chart_type: type,
    statistic: "pct",
    classifying_var: null,
    number_format: { ...DEFAULT_NUMBER_FORMAT },
    sort: { ...DEFAULT_SORT, topbox_codes: [] },
    template_slot: "s1",
    elements: { ...DEFAULT_ELEMENTS },
    scatter_xy: null,
    show_not_answered: false,
    show_empty_categories: false,
    not_answered_codes: null,
    category_label_overrides: [],
    slide_title: opts?.slide_title ?? null,
    slide_description: null,
    options: { bullets: opts?.bullets ?? [] },
  };
}

/** Assign template_slot by position: s1..sN. */
export function normalizeSlots(charts: ChartSpec[]): ChartSpec[] {
  return charts.map((c, i) => ({ ...c, template_slot: `s${i + 1}` }));
}
