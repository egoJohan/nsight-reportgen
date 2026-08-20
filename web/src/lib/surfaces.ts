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

/** The page shell: width, gutters and vertical rhythm.
 *
 * Every page had been spelling its own — max-w-4xl/6xl/3xl with py-8/12/16 —
 * so moving between Asiakkaat, a tutkimus and Asetukset shifted the content
 * sideways and changed the top margin. One definition, so they line up.
 */
export const PAGE = "mx-auto w-full max-w-6xl px-6 py-8";

/** The heading scale. Three levels, one definition each.
 *
 * There were eleven variants across the app — h1 at both 2xl and 3xl, and the
 * same kind of section heading at text-base in one panel and text-sm in the
 * next — so two pages showing the same kind of thing did not look related.
 *
 * PAGE_TITLE names what you are looking at (a customer, a tutkimus, a report).
 * SECTION_TITLE divides a page into parts. PANEL_TITLE labels one control
 * group inside a panel. OVERLINE is for the small muted labels inside dialogs,
 * which are labels rather than headings.
 */
export const PAGE_TITLE = "text-2xl font-semibold tracking-tight";
export const PAGE_SUB = "mt-1 text-sm text-muted-foreground";
export const SECTION_TITLE = "text-base font-semibold tracking-tight";
export const PANEL_TITLE = "text-sm font-semibold";
/** A section heading with its own action beside it — "Tutkimukset" + "Uusi
 *  tutkimus". One per list, so a page with several lists never has a single
 *  button whose target the reader has to infer. */
export const SECTION_HEADER =
  "mt-8 flex items-center justify-between gap-3";

export const OVERLINE =
  "text-xs font-medium uppercase tracking-wide text-muted-foreground";

/** The header block: title on the left, actions on the right, one gap below.
 *  Matches the tutkimus page, which is the layout the others are aligned to. */
export const PAGE_HEADER = "mb-8 flex items-start justify-between gap-4";

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
