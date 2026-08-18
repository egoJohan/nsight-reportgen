/**
 * The one definition of a "surface" — anything that sits on the page background.
 *
 * Every page renders over the tiled backdrop (see TiledBackdrop), so a surface
 * that forgets its fill goes translucent and the tile shows through the text.
 * That happened three different ways at once: bg-surface here, bg-surface/80 with a
 * blur there, and no fill at all on the report and question lists.
 *
 * So the fill lives here, once. Import these instead of retyping the classes —
 * a row that spells its own styling is a row that will drift.
 *
 * The fill is `--surface`, not `--card`: card is pure white in light mode and
 * vanishes against the backdrop. Surface carries a hint of blue-grey so a panel
 * reads as its own thing. Change the tint in index.css, not here.
 */

/** A bordered container holding a divided list (reports, questions). */
export const PANEL = "overflow-hidden rounded-xl border bg-surface";

/** A standalone clickable row (a customer, a tutkimus, a recent report). */
export const ROW =
  "group flex w-full items-center justify-between rounded-lg border bg-surface p-4 " +
  "text-left transition-colors hover:bg-accent";

/** "Nothing here yet" — dashed, but still opaque. */
export const EMPTY = "rounded-lg border border-dashed bg-surface p-10 text-center";

/** A failed fetch. Tinted rather than bg-surface, but deliberately opaque too. */
export const ERROR =
  "rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm";
