import type {
  ChartElements,
  ChartSpec,
  NumberFormat,
  Question,
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
  { id: "themes", label: "Key themes" },
  { id: "wordcloud", label: "Word Cloud" },
];

export const STACKED = new Set<string>([
  "stacked_vertical_bar",
  "stacked_horizontal_bar",
]);

export const SCATTER = "scatter";

// The deck's slide aspect ratio as a Tailwind class — the single knob that keeps
// every preview (Design + Overview grid) matched to the rendered slide. The deck
// renders 16:9 widescreen (13.333"×7.5"); use "aspect-[4/3]" for 4:3.
export const SLIDE_ASPECT = "aspect-video";

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
  // Author-written: a heading plus markdown bullets, no AI.
  special_blank: "Empty slide",
};

//: Which slide this one was copied from. Its presence is what marks a slide as
//: a duplicate; the value is kept because it costs nothing and says where it
//: came from when somebody reads the document.
const DUPLICATE_KEY = "copied_from";

/** Was this slide made by copying another?
 *
 *  It is the only slide the Select page cannot remove — a chart slide's copy
 *  shares its question with the original, so unticking that question hides both,
 *  and a special slide never had a row there. So it is the only slide that
 *  carries its own delete.
 */
export function isDuplicateSlide(chart: {
  options?: Record<string, unknown> | null;
}): boolean {
  return Boolean(chart.options && DUPLICATE_KEY in chart.options);
}

/** A slide, copied to sit directly below itself.
 *
 *  A chart slide's copy is the same slide with a new id: what is worth copying
 *  is the configuration — the chart type, the split, the sort — and the point is
 *  to change one thing about it.
 *
 *  A SPECIAL slide's copy needs more than that. Special slides belong to a
 *  GROUP: regenerating the conclusions replaces every page of that group with
 *  freshly written ones, so a copy that kept the group would vanish the next
 *  time the original was regenerated. The copy gets its own ref and its own
 *  group, and stands alone — its words come with it and are then the author's
 *  to edit.
 */
export function copySlideInDeck<C extends {
  chart_type: string;
  question_ref: string;
  slide_id?: string;
  options?: Record<string, unknown> | null;
}>(charts: readonly C[], index: number, slideId: string): C[] {
  const from = charts[index];
  if (!from) return [...charts];
  // Marked as a duplicate, because nothing about its shape says so and it is
  // the one slide Select cannot reach: a chart slide's copy shares its
  // question, so the catalog's single row covers both, and a special slide's
  // copy has no row at any time. The mark rides in the slide's free-form
  // options, which the report document passes through unchanged.
  let copy = {
    ...from,
    slide_id: slideId,
    options: { ...(from.options ?? {}), [DUPLICATE_KEY]: from.question_ref },
  } as C;
  if (isSpecialSlide(from)) {
    const ref = specialRef(from.chart_type);
    copy = {
      ...copy,
      question_ref: ref,
      options: { ...(copy.options ?? {}), group: ref },
    } as C;
  }
  const out = [...charts];
  out.splice(index + 1, 0, copy);
  return out;
}

/** A slide, taken out of the deck for good.
 *
 *  Unticking a question HIDES its slides, which is what makes a re-tick put
 *  them back where they were. That leaves nothing to remove a slide with, and a
 *  copy has nowhere else to be removed from: it has no catalog row of its own,
 *  and unticking the question it came from would hide the original with it.
 *
 *  Deleting a question's slide is not the end of it — ticking the question in
 *  Select builds a new one at its place in the file's order. What is lost is
 *  the configuration on this particular slide, which is the point of asking.
 */
export function removeSlideInDeck<C>(charts: readonly C[], index: number): C[] {
  if (index < 0 || index >= charts.length) return [...charts];
  return charts.filter((_c, i) => i !== index);
}

/** Tick or untick a question in the catalog, without ever moving a slide.
 *
 *  Unticking used to DELETE every slide showing the question, so ticking it
 *  again built a new slide and had to guess where it went — reported as "when I
 *  untick and tick a question it jumps as first. It should not relocate, it
 *  should appear to its natural location." Nothing can guess it: the deck's
 *  order is the author's, not the file's, and the only thing that knows where
 *  the slide was is the slide.
 *
 *  So unticking hides it where it stands and ticking shows it again — position
 *  intact, and with it the headline, the subtitle and every other edit that
 *  used to be thrown away by a mis-click. Only a question with no slide at all
 *  is inserted, and that one goes to its place in SAV order.
 */
export function toggleQuestionInDeck<C extends {
  chart_type: string;
  question_ref: string;
  excluded?: boolean;
}>(
  charts: readonly C[],
  qid: string,
  makeNew: () => C,
  rankOf: (ref: string) => number
): C[] {
  const own = charts.filter((c) => c.question_ref === qid);
  if (own.length) {
    // Every slide showing it, comparison slides included: leaving one behind
    // orphans a slide for a question the list says is not in the report.
    const hide = own.some((c) => !c.excluded);
    return charts.map((c) =>
      c.question_ref === qid ? { ...c, excluded: hide } : c
    );
  }
  const out = [...charts];
  out.splice(insertionIndex(out, rankOf(qid), rankOf), 0, makeNew());
  return out;
}

/** Where a question slide belongs in a deck, by SAV order.
 *
 *  Among the QUESTION slides only: it goes before the first one that comes
 *  after it in the file, and after the last one otherwise. Special slides are
 *  left exactly where the author put them, which is the whole point.
 *
 *  The scan this replaced looked for a conclusion slide to insert before,
 *  because a conclusion trails a deck. In a deck that OPENS with its
 *  conclusions it found one at index 0, so every re-ticked question landed
 *  first — reported as "when I untick and tick a question it jumps as first".
 *  Where the author put a special slide is not a fact this needs to know.
 */
export function insertionIndex(
  charts: readonly { chart_type: string; question_ref: string }[],
  newRank: number,
  rankOf: (ref: string) => number
): number {
  let lastQuestion = -1;
  for (let i = 0; i < charts.length; i++) {
    // Anything that is not a question slide is left where it is. Not only the
    // SPECIAL slides: a demographics grid and a themes summary are slides of
    // their own with a synthetic ref, and reading one as a question of unknown
    // rank made the scan stop at it — a report with a Demographics section,
    // which sits at the front, took every newly ticked question above it.
    if (isSpecialSlide(charts[i]) || rendersFullSlide(charts[i])) continue;
    if (rankOf(charts[i].question_ref) > newRank) return i;
    lastQuestion = i;
  }
  // After every question slide there is. With none, the deck is all special
  // slides: go to the end, unless a conclusion is sitting there — a deck that
  // ENDS with its conclusions keeps them last.
  if (lastQuestion >= 0) return lastQuestion + 1;
  const last = charts[charts.length - 1];
  return last && last.chart_type === "special_conclusion"
    ? charts.length - 1
    : charts.length;
}

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

// ── AI title staleness ─────────────────────────────────────────────────────
// A generated slide title is tied to the DATA it was written about, never to the
// design. Compare titleDataKey's return value against the chart's stored
// slide_title_key: unequal (or absent) means the title needs a fresh look;
// equal means don't touch it, no matter what else changed. Mirrors
// previewContentKey in queries.ts, which does the same split for the PNG.
//
// IN, because each one changes what a good title would say:
// - question_ref: a different question is a different topic outright.
// - classifying_var / classifying_var_2: splitting the answers by a variable
//   changes which findings even exist to summarise.
// - resolved.text / resolved.variables: what this question_ref CURRENTLY
//   resolves to under the report's grouping — a battery/multi's synthetic
//   question can be renamed or re-scoped (regrouped) without question_ref
//   itself changing, and text/variables is the one place that shows up.
//   `resolved` comes from useRegroupedQuestions, the same call the caller
//   already makes to render question text elsewhere, so no extra fetch.
// - category_label_overrides: the AI endpoint doesn't read these YET, but a
//   rename that merges/relabels categories is exactly the kind of edit a
//   title should react to once it does — keying on it now costs nothing and
//   avoids a second migration later.
// - statistic / show_not_answered / not_answered_codes: all three are sent to
//   POST .../ai/slide-title (see runTitle in ReportWizard) and feed compute()
//   directly — switching "% of respondents" to "mean" changes the very number
//   the title reports on, not how it's drawn.
//
// OUT, because none of them change the ANSWER, only how it's presented:
// template_ref, chart_type, colours/elements, sort order, number_format,
// footer_note, row_summary_* (a display column, not a different finding).
export function titleDataKey(
  chart: ChartSpec,
  resolved: Pick<Question, "text" | "variables"> | undefined
): string {
  return JSON.stringify([
    chart.question_ref,
    chart.classifying_var ?? null,
    chart.classifying_var_2 ?? null,
    // Which groups the slide is drawn on. The headline is a sentence about
    // THESE respondents: duplicate a slide, tick another group, and the one
    // written about the first group is no longer true of what is on the screen.
    chart.classifying_values ?? null,
    resolved?.text ?? null,
    resolved?.variables ?? null,
    chart.category_label_overrides,
    chart.statistic,
    chart.show_not_answered,
    chart.not_answered_codes ?? null,
  ]);
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

// Human labels for a question's kind, shown in deck/list row subtitles.
const KIND_LABELS: Record<string, string> = {
  single: "Single",
  multi: "Multi",
  battery: "Battery",
  comparison: "Comparison",
};

/** Deck/list row subtitle: "<Chart Type>, <Question Type>" (e.g. "Pie Chart,
 * Battery"), or "Bullets, Special" for a special slide. Shared by the Select deck
 * and the Design slide list so both read identically. */
export function slideSubtitle(
  chart: ChartSpec,
  questionMap: Map<string, Question>
): string {
  if (isSpecialSlide(chart)) return "Bullets, Special";
  const q = questionMap.get(chart.question_ref);
  const kind = q ? KIND_LABELS[q.kind] ?? q.kind : null;
  return kind
    ? `${chartTypeLabel(chart.chart_type)}, ${kind}`
    : chartTypeLabel(chart.chart_type);
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
  // The same question asked the other way round: where the DISSATISFACTION sits.
  // Not a reversed top-box sort — that ranks by the high end read backwards, which
  // says something different whenever the mass sits in the middle of the scale.
  { id: "bottom2_sum", label: "Bottom 2 sum" },
  { id: "bottom3_sum", label: "Bottom 3 sum" },
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
  hide_below_pct: null,
};

export const DEFAULT_ELEMENTS: ChartElements = {
  title: true,
  subtitle: true,
  legend: true,
  n: true,
  axis_names: true,
  filter_var: true,
  data_labels: true,
};

// Survey order by default: the SAV's own category order is the order the
// respondent saw and the order the analyst reads the questionnaire in, so a
// fresh chart matches the source until someone decides otherwise. (Johan)
export const DEFAULT_SORT: SortSpec = {
  basis: "data_order",
  topbox_codes: [],
  descending: true,
};

/**
 * Default header for a row-summary function (mirrors the backend `default_label`
 * in reportbuilder/model/report.py). Used as the placeholder for the editable
 * "Summary header" field.
 */
export function defaultRowSummaryLabel(fn?: string): string {
  switch (fn) {
    case "top2_sum": return "Top 2";
    case "top3_sum": return "Top 3";
    case "bottom2_sum": return "Bottom 2";
    case "bottom3_sum": return "Bottom 3";
    case "sum": return "Sum";
    case "mean": return "Keskiarvo";
    case "net": return "Net";
    default: return "";
  }
}

/**
 * Build a fresh ChartSpec for a question with sensible defaults.
 * template_slot is assigned by position later via normalizeSlots().
 */
export function makeChart(
  questionRef: string,
  suggestedChartType: string
): ChartSpec {
  const chartType = suggestedChartType || "vertical_bar";
  return {
    question_ref: questionRef,
    chart_type: chartType,
    statistic: "pct",
    classifying_var: null,
    number_format: { ...DEFAULT_NUMBER_FORMAT },
    // Survey order, stacked bars included: "always", per Johan. A battery used
    // to default to Top-2-sum so the most-agree statement led; that is now a
    // choice the author makes rather than one we make for them.
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
    slide_title_key: null,
    slide_description: null,
    footer_note: null,
    // Auto-detect the cross-tab percentage direction from the variables' roles.
    percent_base: "auto",
    show_total: "auto",
    // Present from the start so the config form patches the FIELD, not options.
    row_summary_fn: "none",
    row_summary_codes: [],
    row_summary_pos_codes: [],
    row_summary_neg_codes: [],
    row_summary_label: "",
    // Identity from creation: the deck may hold TWO slides for one question (the
    // total-level one and the same result split by another variable), and
    // question_ref cannot tell them apart.
    slide_id: newSlideId(),
  };
}

/** A stable per-chart id. question_ref is no longer unique — a comparison section
 * adds a second slide for a question that already has a total-level one. */
export function newSlideId(): string {
  return typeof crypto !== "undefined" && crypto.randomUUID
    ? crypto.randomUUID().slice(0, 8)
    : Math.random().toString(36).slice(2, 10);
}

/** Chart types that can draw more than one series. A pie cannot — which is why a
 * total-level pie must become a clustered bar when split into groups.
 * (spec 2026-08-02-compare-groups-section §2) */
const MULTI_SERIES_CAPABLE = new Set<string>([
  "horizontal_bar",
  "vertical_bar",
  "line",
  "radar",
  "combo",
  "scatter",
  "stacked_horizontal_bar",
  "stacked_vertical_bar",
]);

export function supportsMultiSeries(chartType: string): boolean {
  return MULTI_SERIES_CAPABLE.has(chartType);
}

/** A comparison slide for `source`, split by `classifyingVar`.
 *
 * - Clears classifying_var_2: with a BANNER classifier the engine rejects a second
 *   classifier outright, so carrying one over would make the slide fail to render.
 * - Carries no slide_title, so generating a dozen slides fires no AI title calls.
 * - Falls back to a clustered bar when the source type cannot show two series. */
export function makeComparisonSlide(
  source: ChartSpec,
  classifyingVar: string
): ChartSpec {
  return {
    ...source,
    slide_id: newSlideId(),
    compare_group: classifyingVar,
    classifying_var: classifyingVar,
    classifying_var_2: null,
    percent_base: "auto",
    chart_type: supportsMultiSeries(source.chart_type)
      ? source.chart_type
      : "horizontal_bar",
    slide_title: null,
    slide_title_key: null,
  };
}

/**
 * Build a fresh special (non-chart) slide spec. Heading goes in slide_title,
 * bullet content in options.bullets. Carries all serde-required ChartSpec
 * fields so the backend report_from_json accepts it like any chart.
 */
// A unique id per special slide. The backend identifies special slides by
// chart_type (not question_ref), so a non-empty ref is safe — and it's required
// so that per-slide state (preview cache, AI-pending flags, updateChartById)
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
    footer_note: null,
    // `group` ties together the pages of one logical special slide (so a regen
    // can replace the whole set); absent for single-page slides.
    options: { bullets: opts?.bullets ?? [], ...(opts?.group ? { group: opts.group } : {}) },
    slide_id: newSlideId(),
  };
}

// Coarse capacity of one special slide's body, in "line units" (one 16pt line ≈
// one unit; a bullet costs its wrapped lines + 1 for the gap). Calibrated to the
// 16:9 bullet box (~5.4" tall ⇒ ~24 units, ~90 chars per ~11.4" line), so a full
// MAX_BULLETS list fits ONE slide and only genuinely long/overflowing content
// spills to a second. This is an INTERIM estimate — precise, font-aware fit
// (measuring against the *template's* font and box) is deferred to the
// configurable-template/productization phase, so nothing here should be relied on
// once fonts/sizes vary per template.
const SPECIAL_LINES_PER_SLIDE = 24;
const SPECIAL_CHARS_PER_LINE = 90;

/** Pack bullets into slide-sized pages by an estimated wrapped-line count, so long
 *  content spans multiple slides instead of overflowing one. Approximate by design. */
export function paginateBullets(bullets: string[]): string[][] {
  const pages: string[][] = [];
  let cur: string[] = [];
  let lines = 0;
  for (const b of bullets) {
    const cost = Math.max(1, Math.ceil(b.length / SPECIAL_CHARS_PER_LINE)) + 1; // +1 spacing
    if (cur.length && lines + cost > SPECIAL_LINES_PER_SLIDE) {
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
    slide_title: opts?.slide_title ?? "Respondents",
    slide_description: null,
    footer_note: null,
    // Every other slide factory mints one, and the preview queue is keyed by
    // it: without an id the deck registration drops the slide and nothing ever
    // asks for its picture, so a demographics grid stayed blank until the
    // report was saved and reopened (the load path backfills ids).
    slide_id: newSlideId(),
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
        slide_title: pages > 1 ? `Respondents (${p + 1}/${pages})` : "Respondents",
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
