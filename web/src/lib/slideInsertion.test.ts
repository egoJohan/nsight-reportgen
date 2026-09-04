import { describe, expect, it } from "vitest";
import { insertionIndex, toggleQuestionInDeck } from "./charts";

/** Reported: "when I untick and tick a question it jumps as first. It should
 *  not relocate, it should appear to its natural location."
 *
 *  The deck it happened in opens with a Conclusions slide — the author put the
 *  conclusions at the FRONT. The old scan walked the deck looking for a
 *  conclusion to insert before, on the assumption that a conclusion trails the
 *  deck, found it at index 0 and put every re-ticked question there.
 */
type Slide = {
  chart_type: string;
  question_ref: string;
  slide_id?: string;
  excluded?: boolean;
  compare_group?: string;
};
const q = (ref: string): Slide => ({ chart_type: "horizontal_bar", question_ref: ref });
const overview: Slide = { chart_type: "special_overview", question_ref: "sp_overview" };
const conclusion: Slide = { chart_type: "special_conclusion", question_ref: "sp_conclusion" };

// SAV order: a, b, c, d
const RANK: Record<string, number> = { a: 0, b: 1, c: 2, d: 3 };
const rankOf = (ref: string) => RANK[ref] ?? Number.POSITIVE_INFINITY;

describe("where a re-ticked question goes back", () => {
  it("lands between its neighbours in SAV order", () => {
    expect(insertionIndex([q("a"), q("b"), q("d")], rankOf("c"), rankOf)).toBe(2);
  });

  it("goes first among the questions when it ranks first", () => {
    expect(insertionIndex([q("b"), q("c")], rankOf("a"), rankOf)).toBe(0);
  });

  it("goes last when it ranks last", () => {
    expect(insertionIndex([q("a"), q("b")], rankOf("d"), rankOf)).toBe(2);
  });

  it("does NOT jump ahead of a conclusion slide the author put first", () => {
    // The bug, exactly: [Conclusions, Study background, b, c] + a
    const deck = [conclusion, overview, q("b"), q("c")];
    expect(insertionIndex(deck, rankOf("a"), rankOf)).toBe(2);
  });

  it("stays inside the question run when specials sit at both ends", () => {
    const deck = [overview, q("a"), q("c"), conclusion];
    expect(insertionIndex(deck, rankOf("b"), rankOf)).toBe(2);
    expect(insertionIndex(deck, rankOf("d"), rankOf)).toBe(3);
  });

  it("puts the first question slide after the specials already there", () => {
    expect(insertionIndex([conclusion, overview], rankOf("a"), rankOf)).toBe(2);
  });

  it("keeps a TRAILING conclusion last when the deck has no questions yet", () => {
    expect(insertionIndex([overview, conclusion], rankOf("a"), rankOf)).toBe(1);
  });

  it("puts a question of unknown rank after the ones it knows", () => {
    expect(insertionIndex([q("a"), q("b")], rankOf("zzz"), rankOf)).toBe(2);
  });
});

describe("unticking a question in the catalog", () => {
  const deck = (): Slide[] => [
    { ...q("b"), slide_id: "s1", excluded: false },
    conclusion,
    { ...q("c"), slide_id: "s2", excluded: false },
    { ...q("c"), slide_id: "s3", compare_group: "g", excluded: false },
  ];
  const made = (): Slide => ({ ...q("a"), slide_id: "new" });

  it("keeps the slide exactly where it is", () => {
    const out = toggleQuestionInDeck(deck(), "c", made, rankOf);
    expect(out.map((c) => c.slide_id ?? c.chart_type)).toEqual(
      ["s1", "special_conclusion", "s2", "s3"]
    );
    expect(out[2].excluded).toBe(true);
  });

  it("takes EVERY slide showing that question, comparison slides included", () => {
    const out = toggleQuestionInDeck(deck(), "c", made, rankOf);
    expect(out.filter((c) => c.question_ref === "c").every((c) => c.excluded)).toBe(true);
  });

  it("ticking it again brings it back in place, with its edits", () => {
    const once = toggleQuestionInDeck(deck(), "c", made, rankOf);
    const twice = toggleQuestionInDeck(once, "c", made, rankOf);
    expect(twice.map((c) => c.slide_id ?? c.chart_type)).toEqual(
      ["s1", "special_conclusion", "s2", "s3"]
    );
    expect(twice.every((c) => !c.excluded)).toBe(true);
  });

  it("a question with no slide yet is added at its place in SAV order", () => {
    const out = toggleQuestionInDeck(deck(), "a", made, rankOf);
    expect(out[0].slide_id).toBe("new");
    expect(out).toHaveLength(5);
  });
});

describe("slides that are not questions but are not 'special' either", () => {
  const grid = {
    chart_type: "demographics_grid",
    question_ref: "sp_demographics_grid_x",
  };

  it("a demographics grid is not something to insert a question before", () => {
    // It is a slide of its own — a grid of small charts — but it is not in
    // SPECIAL_SLIDE_LABELS, so the scan read it as a question of unknown rank
    // (Infinity) and stopped there. A report with a Demographics section, which
    // sits at the front, took every newly ticked question above it.
    const deck = [{ chart_type: "special_demographics", question_ref: "sp_d" },
                  grid, q("b"), q("c")];
    expect(insertionIndex(deck, rankOf("a"), rankOf)).toBe(2);
    expect(insertionIndex(deck, rankOf("d"), rankOf)).toBe(4);
  });

  it("a themes slide is not one either", () => {
    const deck = [{ chart_type: "themes", question_ref: "open1" }, q("c")];
    expect(insertionIndex(deck, rankOf("d"), rankOf)).toBe(2);
  });
});
