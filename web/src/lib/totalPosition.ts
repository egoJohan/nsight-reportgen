/** Whether a chart draws a Total the author can move — the editor offers
 *  "Total position" only then. (2026-09-11)
 *
 *  Three things decide it:
 *  - a classifying variable: without one the chart has a single series, and a
 *    Total that is the only thing drawn has nowhere else to go;
 *  - no CROSSED second variable: two variables crossed into combos ("Naiset ·
 *    18-39") carry no Total at all, whatever "Total column" says. Separate
 *    panels do not cross them, and each panel keeps its own Total;
 *  - the "Total column" setting as the engine resolves it. That part is a copy
 *    of `resolve_show_total` (stats/percent_base.py); both copies are pinned to
 *    one table, in totalPosition.test.ts and test_total_position.py. */
export interface TotalInputs {
  classifying_var?: string | null;
  classifying_var_2?: string | null;
  options?: Record<string, unknown> | null;
  show_total?: string;
  chart_type: string;
  statistic?: string;
  percent_base?: string;
}

const STACKED = new Set(["stacked_horizontal_bar", "stacked_vertical_bar"]);
const WITHIN_CATEGORY = new Set(["auto", "question", "classifier"]);

export function drawsTotal(chart: TotalInputs): boolean {
  if (!chart.classifying_var) return false;
  const layout = (chart.options?.xtab_layout as string | undefined) ?? "auto";
  if (chart.classifying_var_2 && layout !== "separate") return false;
  const mode = chart.show_total ?? "auto";
  if (mode === "on") return true;
  if (mode === "off") return false;
  // A stacked bar's Total is a 100% reference on the same scale as every bar.
  if (STACKED.has(chart.chart_type)) return true;
  const withinCategoryPct =
    (chart.statistic ?? "pct") === "pct" && WITHIN_CATEGORY.has(chart.percent_base ?? "auto");
  return !withinCategoryPct;
}
