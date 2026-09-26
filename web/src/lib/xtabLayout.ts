/** What a two-variable clustered bar chart is drawn as, for the layout selector.
 *
 *  The selector no longer offers "Combined panel" (the old "auto") on clustered
 *  bars: it was a rule, not a layout, so an author could not tell what the slide
 *  would look like (Johan, 2026-09-26). A slide saved with it — or with nothing —
 *  keeps being DRAWN by that rule, and the selector SHOWS the layout the rule
 *  gives, from the same numbers the renderer uses (`_resolve_xtab_layout` in
 *  bars.py): small multiples in one row when there are at least two groups of the
 *  first variable and more than eight combinations, grouped bars otherwise.
 *
 *  An explicit choice is shown as it is. */
export interface LayoutInputs {
  classifying_var?: string | null;
  classifying_var_2?: string | null;
  classifying_values?: string[] | null;
  options?: Record<string, unknown> | null;
}

export function shownXtabLayout(
  chart: LayoutInputs,
  offered: string[],
  nValues: (name: string | null | undefined) => number | undefined,
): string {
  const stored = (chart.options?.xtab_layout as string | undefined) ?? "auto";
  if (offered.includes(stored)) return stored;
  const picked = chart.classifying_values?.length;
  const nPrimary = picked || nValues(chart.classifying_var) || 0;
  const nSecond = nValues(chart.classifying_var_2) || 0;
  const drawn = nPrimary >= 2 && nPrimary * nSecond > 8 ? "small_multiples" : "grouped";
  return offered.includes(drawn) ? drawn : (offered[0] ?? stored);
}
