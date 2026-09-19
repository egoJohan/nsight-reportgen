/** How long an edit waits before its slide is queued to render.
 *
 *  Free text is typed in bursts of words with pauses inside a sentence, and
 *  every pause longer than the wait renders a half-written headline nobody
 *  asked to see — on a render host with one core. So text waits long enough to
 *  coalesce those pauses: 2s, where one seven-word headline costs one render
 *  instead of seven.
 *
 *  A dropdown or a toggle has no second half. Nothing follows the change, and
 *  making the author wait out the text window cost 2.6s to the first picture
 *  against 1.0s. So everything that is not free text settles quickly.
 *  (perf, 2026-09-19)
 */
export const TEXT_SETTLE_MS = 2000;
export const CONTROL_SETTLE_MS = 250;

/** The chart fields an author TYPES into. Everything else is a control. */
const TEXT_FIELDS = new Set([
  "slide_title",
  "slide_title_key",
  "slide_description",
  "footer_note",
  "axis_x_title",
  "axis_y_title",
  "row_summary_label",
  "category_label_overrides",
  "series_label_overrides",
]);

/** Keys of `options` that hold typed text. */
const TEXT_OPTIONS = new Set(["bullets"]);

type Chart = Record<string, unknown> & { slide_id?: string | null };

function sameJson(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Whether the only differences between two versions of a slide are typed text. */
function onlyTextChanged(before: Chart, after: Chart): boolean {
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  for (const key of keys) {
    if (sameJson(before[key], after[key])) continue;
    if (TEXT_FIELDS.has(key)) continue;
    if (key === "options") {
      const a = (before.options ?? {}) as Record<string, unknown>;
      const b = (after.options ?? {}) as Record<string, unknown>;
      const optionKeys = new Set([...Object.keys(a), ...Object.keys(b)]);
      for (const k of optionKeys) {
        if (!sameJson(a[k], b[k]) && !TEXT_OPTIONS.has(k)) return false;
      }
      continue;
    }
    return false;
  }
  return true;
}

/** The wait for this change: the text wait only when every slide that changed
 *  changed in typed text alone; the short one otherwise — including a slide
 *  added or removed. `previous` is what was last queued, by slide id. */
export function settleDelay(previous: Map<string, Chart>, charts: Chart[]): number {
  let changed = false;
  const ids = new Set<string>();
  for (const chart of charts) {
    const id = chart.slide_id ?? "";
    ids.add(id);
    const before = previous.get(id);
    if (before === undefined) return CONTROL_SETTLE_MS;
    if (sameJson(before, chart)) continue;
    changed = true;
    if (!onlyTextChanged(before, chart)) return CONTROL_SETTLE_MS;
  }
  for (const id of previous.keys()) {
    if (!ids.has(id)) return CONTROL_SETTLE_MS;
  }
  return changed ? TEXT_SETTLE_MS : CONTROL_SETTLE_MS;
}
