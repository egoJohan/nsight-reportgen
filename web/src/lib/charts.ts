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
  { id: "combo", label: "Combo Chart" },
];

export const STACKED = new Set<string>([
  "stacked_vertical_bar",
  "stacked_horizontal_bar",
]);

export const SCATTER = "scatter";

export function isStacked(chartType: string): boolean {
  return STACKED.has(chartType);
}

export function chartTypeLabel(id: string): string {
  return CHART_TYPES.find((c) => c.id === id)?.label ?? id;
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
    slide_title: null,
    slide_description: null,
  };
}

/** Assign template_slot by position: s1..sN. */
export function normalizeSlots(charts: ChartSpec[]): ChartSpec[] {
  return charts.map((c, i) => ({ ...c, template_slot: `s${i + 1}` }));
}
