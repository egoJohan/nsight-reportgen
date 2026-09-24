import type { DatasetUsage } from "./api";

/** The confirmation shown before a dataset is deleted.
 *
 *  Its study's LAST dataset makes the study read-only for good: report
 *  definitions go, the decks already generated stay (spec
 *  docs/superpowers/specs/2026-09-24-dataset-deletion-design.md). Reports that
 *  were never generated are lost entirely, so they are NAMED — a list is
 *  something an analyst can weigh, a count is not. One of several datasets
 *  goes on its own, and the warning says which file the reports use next. */
export interface DatasetDeleteWarning {
  paragraphs: string[];
  /** The names of the reports that will be deleted entirely. */
  lost: string[];
  confirm: string;
  /** Offer the "keep the generated decks" tick box: there are decks to keep.
   *  ("If there is deck/PDF downloadable, let's have a tick box whether to
   *  leave those or delete." — Johan, 2026-09-24) */
  offerKeepDecks: boolean;
  /** How many decks the tick box is about. */
  deckCount: number;
}

export function datasetDeleteWarning(
  usage: DatasetUsage | null,
  fileName: string,
  keepDecks = true
): DatasetDeleteWarning {
  if (usage && !usage.last_dataset) {
    const next = usage.remaining.join(", ");
    return {
      paragraphs: [
        `This removes the file "${fileName}" and its curation. ` +
          (next ? `The study's reports will use "${next}" from now on.` : ""),
      ].map((p) => p.trim()),
      lost: [],
      confirm: "Delete dataset",
      offerKeepDecks: false,
      deckCount: 0,
    };
  }
  const withDeck = usage?.with_deck ?? [];
  const offerKeepDecks = withDeck.length > 0;
  if (offerKeepDecks && !keepDecks) {
    const lost = [...withDeck, ...(usage?.without_deck ?? [])].sort();
    return {
      paragraphs: [
        "This makes the study read-only for good, and deletes every report " +
          "together with its generated deck. Nothing of the reports remains; " +
          "the empty study can then be deleted too.",
        `${lost.length} ${lost.length === 1 ? "report is" : "reports are"} deleted:`,
      ],
      lost,
      confirm: "Delete dataset and every report",
      offerKeepDecks,
      deckCount: withDeck.length,
    };
  }
  const lost = usage?.without_deck ?? [];
  return {
    paragraphs: [
      "This makes the study read-only for good. Report definitions are " +
        "deleted: reports can no longer be opened, edited, duplicated or " +
        "generated again. Only the decks already generated remain, for " +
        "download as PDF and PPTX.",
      ...(lost.length
        ? [
            `${lost.length} ${lost.length === 1 ? "report has" : "reports have"} ` +
              "no generated deck and will be deleted entirely:",
          ]
        : []),
    ],
    lost,
    confirm: "Delete dataset and make the study read-only",
    offerKeepDecks,
    deckCount: withDeck.length,
  };
}
