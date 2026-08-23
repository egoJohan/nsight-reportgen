import type { ChartSpec } from "./api";

/** What a slide's IMAGE does not depend on.
 *
 * The list is short, and it is the only place this judgement is recorded:
 *
 *  - `slide_id`, `compare_group` — identity and provenance, never drawn
 *  - `slide_title_key`           — the title producer's own bookkeeping
 *  - `template_slot`, `excluded` — where the slide sits in the deck, not what
 *                                  it shows
 *
 * `template_slot` earns its place twice over: `normalizeSlots` rewrites it to
 * `s${i + 1}` for EVERY chart in the report on any reorder (see charts.ts), so
 * hashing it would re-render all sixty slides when the author drags one.
 */
export const IMAGE_FINGERPRINT_IGNORED = [
  "slide_id",
  "compare_group",
  "slide_title_key",
  "template_slot",
  "excluded",
] as const;

/** The parts of "which image is this?" that do not live on the chart itself. */
export interface RenderContext {
  /** The report's own template choice; "" when it inherits one. */
  templateRef: string;
  /** Which report — the backend resolves a template through it. */
  reportId: string;
  /** The report's grouping override, already serialised. */
  groupingKey: string;
  /** Which renderer draws the slide: compositor or LibreOffice. */
  renderTitle: boolean;
}

/**
 * What this slide's image depends on — everything, minus what provably cannot
 * change a pixel.
 *
 * By EXCLUSION, deliberately. This replaced an allow-list of twenty-five named
 * fields, which meant every new ChartSpec field had to be remembered there or
 * the preview silently kept showing the old image — a bug that looks like a
 * broken renderer, and that no reviewer of the new field would think to look
 * for. Hashing by exclusion inverts the failure: forget to exclude something
 * and you pay one extra render, which nobody files a ticket about.
 *
 * The slide title is IN, on purpose. It is baked into the PNG on both render
 * paths, so a title landing makes its own image stale and the slide re-renders
 * exactly once — the ordering enforces itself, with no rule for anyone to
 * maintain.
 */
export function imageFingerprint(chart: ChartSpec, ctx: RenderContext): string {
  const ignored = new Set<string>(IMAGE_FINGERPRINT_IGNORED);
  const rest: Record<string, unknown> = {};
  // Sorted, because the output is a string: a chart rebuilt by a spread has the
  // same fields in a different order and must not look like it changed.
  for (const key of Object.keys(chart).sort()) {
    if (!ignored.has(key)) rest[key] = (chart as unknown as Record<string, unknown>)[key];
  }
  return JSON.stringify([
    rest,
    ctx.templateRef,
    ctx.reportId,
    ctx.groupingKey,
    ctx.renderTitle,
  ]);
}
