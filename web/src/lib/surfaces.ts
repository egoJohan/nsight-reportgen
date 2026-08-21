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
/** A section heading with its own action beside it — "Studies" + "Uusi
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

/** A list-item row denser than ROW: a checkbox or status mark, a title that
 *  may run to two lines, and a badge/menu at the trailing edge — the case's
 *  question list and the report's Select step both list questions this way.
 *  Same border/fill/hover as ROW, tighter padding and an explicit gap so the
 *  leading mark and trailing badge don't need justify-between to place them.
 *  Callers add their own state (selected/disabled/highlighted) and, where a
 *  kebab menu overlays the row, "pr-11" to keep text out from under it. */
export const ITEM_ROW =
  "group flex w-full items-center gap-3 rounded-lg border bg-surface py-2.5 pr-3 pl-3 " +
  "text-left transition-colors hover:bg-accent";

/** A question/item title inside an ITEM_ROW — same size, line-height and
 *  2-line clamp wherever a question is listed, so long text wraps the same
 *  way in the case list and the Select step alike. */
/** A selected/included item row.
 *
 *  Tinted with --accent, NOT --primary. This app's primary is near-black
 *  (oklch 0.205) because the palette is neutral, so a primary tint does not
 *  read as "chosen", it reads as "dirty" — and at 6% it landed DARKER than the
 *  hover state, inverting the hierarchy. Lightness runs: row 0.965 > selected
 *  ~0.948 > hover 0.928, so hovering a selected row still darkens it.
 *
 *  An OPAQUE tint, not `bg-primary/5`. An alpha tint replaces ITEM_ROW's
 *  `bg-surface` rather than sitting on it, so the tiled page backdrop shows
 *  through and the row reads as semi-transparent — while the same row on the
 *  case page, which keeps bg-surface, reads solid. Mixing the tint INTO the
 *  surface colour keeps one opaque surface everywhere.
 */
export const ITEM_ROW_SELECTED =
  "border-primary/40 bg-[color-mix(in_oklch,var(--surface),var(--accent)_45%)]";

/** The same idea for an item that cannot be chosen. */
export const ITEM_ROW_DISABLED =
  "cursor-not-allowed border-transparent opacity-60 " +
  "bg-[color-mix(in_oklch,var(--surface),var(--muted)_60%)]";

export const ITEM_TITLE = "text-sm leading-snug line-clamp-2 break-words";

/** "Nothing here yet" — dashed, but still opaque. */
export const EMPTY = "rounded-lg border border-dashed bg-surface p-10 text-center";

/** A failed fetch. Tinted rather than bg-surface, but deliberately opaque too. */
export const ERROR =
  "rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm";
