/**
 * Which decimal controls a chart's Number format panel should offer.
 *
 * The Manual panel always drew BOTH "% decimals" and "Mean decimals", whatever
 * the chart measured. On a percentage chart the mean box does nothing at all —
 * the renderer picks `pct_decimals` when the statistic is "pct" and
 * `mean_decimals` when it is "mean", never both — so half the panel was a
 * control that lied. Reported as: the text says "mean decimals" even when you
 * are setting the decimals of percentages.
 *
 * So a chart that shows one kind of number gets one box, called "Decimals".
 *
 * The exception is the combo, which since 2026-09-16 really does carry two
 * measures at once: percentages on its bars and the secondary variable's mean
 * on its line, each formatted from its own field. There the two boxes are not
 * noise and keep their specific names — naming them both "Decimals" would be
 * the opposite mistake. (Johan, 2026-09-16)
 */

export type DecimalField = "pct" | "mean";

export interface NumberFormatChart {
  statistic: string;
  chart_type: string;
  options?: Record<string, unknown> | null;
}

/** True when this chart draws a percentage AND a mean, on two scales. */
export function hasTwoMeasures(chart: NumberFormatChart): boolean {
  return (
    chart.chart_type === "combo" &&
    Boolean(chart.options?.["combo_secondary"]) &&
    // A categorical secondary is the share of one of its groups — a percentage,
    // so there is no mean on the slide to give decimals to. (2026-09-17)
    !chart.options?.["combo_secondary_value"]
  );
}

/**
 * The decimal fields worth showing, in display order.
 *
 * Empty for a statistic whose numbers ignore both (`count` and the summary
 * family are drawn with no decimals at all): showing a box that changes
 * nothing is what this is fixing, so it must not be traded for a different one.
 */
export function decimalFields(chart: NumberFormatChart): DecimalField[] {
  if (hasTwoMeasures(chart)) return ["pct", "mean"];
  if (chart.statistic === "pct") return ["pct"];
  if (chart.statistic === "mean") return ["mean"];
  return [];
}

/** The label for one field — specific only when both are on screen together. */
export function decimalFieldLabel(
  field: DecimalField,
  fields: DecimalField[],
): string {
  if (fields.length < 2) return "Decimals";
  return field === "pct" ? "% decimals" : "Mean decimals";
}

/** Whether the "% sign" toggle does anything: only percentages carry one. */
export function showsPercentSign(chart: NumberFormatChart): boolean {
  return decimalFields(chart).includes("pct");
}
