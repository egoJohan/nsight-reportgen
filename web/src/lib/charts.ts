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
  { id: "themes", label: "Themes (open-ended)" },
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

/** True when the slide is rendered as a bullet list (special slides or an
 *  open-ended "themes" summary) rather than a data chart — so it uses the
 *  full-PNG preview and a bullets editor. */
export function isThemes(chart: { chart_type: string }): boolean {
  return chart.chart_type === "themes";
}

export function rendersAsBullets(chart: { chart_type: string }): boolean {
  return isSpecialSlide(chart) || isThemes(chart);
}

/** A multi-chart demographics grid slide (options.charts = [{question_ref,chart_type}]). */
export function isDemographicsGrid(chart: { chart_type: string }): boolean {
  return chart.chart_type === "demographics_grid";
}

/** True when the whole slide is rendered server-side (bullets or a chart grid),
 *  so the preview shows the full PNG with no frontend title overlay. */
export function rendersFullSlide(chart: { chart_type: string }): boolean {
  return rendersAsBullets(chart) || isDemographicsGrid(chart);
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
  { id: "data_order", label: "Survey order" },
  { id: "mean", label: "Mean" },
  { id: "count", label: "Count" },
  // Stacked bars (battery statements OR a classifier's group bars): order the BARS by
  // the summed highest scale levels, so the most-"agree" bar leads — the scale stack
  // itself stays 1..N.
  { id: "topbox_sum", label: "Top 2 sum" },
  { id: "top3_sum", label: "Top 3 sum" },
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
  const chartType = suggestedChartType || "vertical_bar";
  // Stacked bars are the scale/battery distribution — default them to "Top 2 sum"
  // (most-agree statement on top); everything else keeps the default percentage sort.
  const isStacked = chartType.startsWith("stacked_");
  return {
    question_ref: questionRef,
    chart_type: chartType,
    statistic: "pct",
    classifying_var: null,
    number_format: { ...DEFAULT_NUMBER_FORMAT },
    sort: {
      ...DEFAULT_SORT,
      basis: isStacked ? "topbox_sum" : DEFAULT_SORT.basis,
      topbox_codes: [],
    },
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
  opts?: { slide_title?: string; bullets?: string[]; group?: string }
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
    // `group` ties together the pages of one logical special slide (so a regen
    // can replace the whole set); absent for single-page slides.
    options: { bullets: opts?.bullets ?? [], ...(opts?.group ? { group: opts.group } : {}) },
  };
}

// Heuristic capacity of one special slide's body, in wrapped text lines.
const SPECIAL_LINES_PER_SLIDE = 12;
const SPECIAL_CHARS_PER_LINE = 64;

/** Pack bullets into slide-sized pages by estimated wrapped-line count, so long
 *  content spans multiple slides instead of overflowing one. */
export function paginateBullets(
  bullets: string[],
  linesPerSlide = SPECIAL_LINES_PER_SLIDE
): string[][] {
  const pages: string[][] = [];
  let cur: string[] = [];
  let lines = 0;
  for (const b of bullets) {
    const cost = Math.max(1, Math.ceil(b.length / SPECIAL_CHARS_PER_LINE)) + 1; // +1 spacing
    if (cur.length && lines + cost > linesPerSlide) {
      pages.push(cur);
      cur = [];
      lines = 0;
    }
    cur.push(b);
    lines += cost;
  }
  if (cur.length) pages.push(cur);
  return pages.length ? pages : [[]];
}

/** Build the slide spec(s) for a special slide whose content may span pages.
 *  One page → one plain-heading slide; multiple → "Heading (n/x)" per page,
 *  all sharing a `group` id so a later regenerate can swap the whole set. */
export function buildSpecialPages(
  type: string,
  heading: string,
  bullets: string[],
  group: string
): ChartSpec[] {
  const pages = paginateBullets(bullets);
  if (pages.length <= 1) {
    return [makeSpecialSlide(type, { slide_title: heading, bullets: pages[0], group })];
  }
  return pages.map((page, i) =>
    makeSpecialSlide(type, {
      slide_title: `${heading} (${i + 1}/${pages.length})`,
      bullets: page,
      group,
    })
  );
}

/** Build a demographics-grid slide spec from per-question cell charts. */
export function makeDemographicsGrid(
  cells: { question_ref: string; chart_type: string }[],
  opts?: { slide_title?: string; group?: string }
): ChartSpec {
  return {
    question_ref: specialRef("demographics_grid"),
    chart_type: "demographics_grid",
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
    slide_title: opts?.slide_title ?? "Vastaajat",
    slide_description: null,
    options: { charts: cells, ...(opts?.group ? { group: opts.group } : {}) },
  };
}

/** Group demographic cell charts into grid slides of up to `per` charts each. */
export function buildDemographicsGrids(
  cells: { question_ref: string; chart_type: string }[],
  group: string,
  per = 4
): ChartSpec[] {
  const pages = Math.ceil(cells.length / per);
  const out: ChartSpec[] = [];
  for (let p = 0; p < pages; p++) {
    out.push(
      makeDemographicsGrid(cells.slice(p * per, (p + 1) * per), {
        slide_title: pages > 1 ? `Vastaajat (${p + 1}/${pages})` : "Vastaajat",
        group,
      })
    );
  }
  return out;
}

/** Assign template_slot by position: s1..sN. */
export function normalizeSlots(charts: ChartSpec[]): ChartSpec[] {
  return charts.map((c, i) => ({ ...c, template_slot: `s${i + 1}` }));
}
