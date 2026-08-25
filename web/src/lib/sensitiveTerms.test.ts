import { describe, expect, it } from "vitest";

import { mergeTerms } from "./sensitiveTerms";

describe("mergeTerms", () => {
  it("lists what the study proposed", () => {
    expect(mergeTerms(["Attendo", "Esperi"], [], [])).toEqual(["Attendo", "Esperi"]);
  });

  it("shows a term typed by hand", () => {
    // The bug this exists to stop: a typed term went into the ticked set but
    // never into the rendered list, so it vanished as you added it and the
    // only way to find out it HAD registered was to save and reload.
    expect(mergeTerms(["Attendo"], [], ["Mehiläinen"])).toEqual([
      "Attendo",
      "Mehiläinen",
    ]);
  });

  it("keeps an accepted term the study no longer proposes", () => {
    // Re-reading the study must not silently drop a name somebody vouched for.
    expect(mergeTerms(["Attendo"], ["Humana"], [])).toEqual(["Attendo", "Humana"]);
  });

  it("does not duplicate a typed term that was already proposed", () => {
    // Otherwise the same name renders twice and the two chips disagree about
    // whether it is ticked.
    expect(mergeTerms(["Attendo"], [], ["Attendo"])).toEqual(["Attendo"]);
  });

  it("treats a term that differs only by case or padding as the same term", () => {
    expect(mergeTerms(["Attendo"], [], ["  attendo  "])).toEqual(["Attendo"]);
  });

  it("ignores blank input", () => {
    expect(mergeTerms(["Attendo"], [], ["", "   "])).toEqual(["Attendo"]);
  });

  it("survives missing server data", () => {
    expect(mergeTerms(undefined, null, ["Attendo"])).toEqual(["Attendo"]);
  });

  it("keeps first-seen order so the list does not jump as you type", () => {
    expect(mergeTerms(["B", "A"], ["C"], ["D"])).toEqual(["B", "A", "C", "D"]);
  });
});
