/**
 * The legend names a slide draws that are not the question's answers — a
 * classifying variable's groups, a combo's secondary series — and their renames.
 *
 * Category labels rename the ANSWERS, which is the whole legend on a pie or a
 * stacked bar. Split by a classifying variable the legend shows GROUPS instead,
 * and those were in no editor at all: "the legend is cut and cannot be edited".
 * They are stored apart (`series_label_overrides`) because a name can be an
 * answer and a group at once ("Kyllä"), and renaming one must not rename the
 * other. (2026-09-17)
 */
import type { ChartSpec } from "./api";

/** The names to list: what the server says the slide draws, minus anything the
 *  answers list above already offers — a name is edited in one place. */
export function legendRows(names: string[], answerLabels: string[]): string[] {
  const answers = new Set(answerLabels);
  return names.filter((n) => !answers.has(n));
}

/** Store, change or remove one rename. Empty, or the name itself, removes it —
 *  the same rule the category labels follow. */
export function withSeriesOverride(
  pairs: [string, string][] | undefined,
  full: string,
  shown: string,
): [string, string][] {
  const rest = (pairs ?? []).filter(([f]) => f !== full);
  const trimmed = shown.trim();
  return trimmed && trimmed !== full ? [...rest, [full, shown]] : rest;
}

/** Settings that cannot change WHICH names the slide draws. Everything else is
 *  in the key, so an unforeseen setting costs a refetch rather than a stale list.
 *  The renames themselves are out: the list is always the data's own names. */
const NOT_ABOUT_NAMES = new Set<string>([
  "slide_id", "slide_title", "slide_title_key", "slide_description", "footer_note",
  "axis_x_title", "axis_y_title", "template_slot", "excluded", "compare_group",
  "number_format", "elements", "sort",
  "category_label_overrides", "series_label_overrides",
]);

export function legendNamesKey(chart: ChartSpec): string {
  const kept = Object.entries(chart as unknown as Record<string, unknown>)
    .filter(([k]) => !NOT_ABOUT_NAMES.has(k))
    .sort(([a], [b]) => a.localeCompare(b));
  return JSON.stringify(kept);
}
