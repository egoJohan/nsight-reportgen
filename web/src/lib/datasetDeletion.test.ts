import { describe, expect, it } from "vitest";

import { datasetDeleteWarning, studyDeleteWarning } from "./datasetDeletion";

describe("datasetDeleteWarning", () => {
  const last = { last_dataset: true, remaining: [], with_deck: ["Delivered"], without_deck: [] };

  it("says the study becomes read-only and only the decks remain", () => {
    const w = datasetDeleteWarning(last, "brandi.sav");
    expect(w.paragraphs[0]).toMatch(/read-only for good/);
    expect(w.paragraphs[0]).toMatch(/Only the decks already generated remain/);
    expect(w.lost).toEqual([]);
    expect(w.paragraphs).toHaveLength(1);
  });

  it("names the reports with no deck, which are lost entirely", () => {
    const w = datasetDeleteWarning(
      { ...last, without_deck: ["Draft A", "Draft B"] }, "brandi.sav");
    expect(w.paragraphs[1]).toBe("2 reports have no generated deck and will be deleted entirely:");
    expect(w.lost).toEqual(["Draft A", "Draft B"]);
  });

  it("uses the singular for one", () => {
    const w = datasetDeleteWarning({ ...last, without_deck: ["Draft"] }, "brandi.sav");
    expect(w.paragraphs[1]).toMatch(/^1 report has no generated deck/);
  });

  it("one of several datasets names the file the reports use next", () => {
    const w = datasetDeleteWarning(
      { last_dataset: false, remaining: ["brandi-v2.sav"], with_deck: [], without_deck: ["X"] },
      "brandi.sav");
    expect(w.paragraphs[0]).toBe(
      'This removes the file "brandi.sav" and its curation. ' +
        'The study\'s reports will use "brandi-v2.sav" from now on.');
    expect(w.lost).toEqual([]);
    expect(w.confirm).toBe("Delete dataset");
  });

  it("without the facts, errs on the side of the stronger warning", () => {
    expect(datasetDeleteWarning(null, "brandi.sav").paragraphs[0]).toMatch(/read-only for good/);
  });

  it("offers the tick box only when there are decks to keep", () => {
    expect(datasetDeleteWarning(last, "brandi.sav").offerKeepDecks).toBe(true);
    expect(datasetDeleteWarning({ ...last, with_deck: [] }, "brandi.sav").offerKeepDecks).toBe(false);
    expect(datasetDeleteWarning(
      { last_dataset: false, remaining: ["b.sav"], with_deck: ["D"], without_deck: [] },
      "a.sav").offerKeepDecks).toBe(false);
  });

  it("unticked, every report and its deck is named as lost", () => {
    const w = datasetDeleteWarning(
      { ...last, without_deck: ["Draft"] }, "brandi.sav", false);
    expect(w.paragraphs[0]).toMatch(/deletes every report together with its generated deck/);
    expect(w.lost).toEqual(["Delivered", "Draft"]);
    expect(w.confirm).toBe("Delete dataset and every report");
  });
});

describe("studyDeleteWarning", () => {
  const none = { last_dataset: true, remaining: [], with_deck: [], without_deck: [] };

  it("no reports: the study is simply deleted", () => {
    const w = studyDeleteWarning(none, "Brändi");
    expect(w.outright).toBe(true);
    expect(w.paragraphs).toEqual([
      "The study “Brändi” has no reports. It is deleted together with the data imported into it."]);
    expect(w.lost).toEqual([]);
    expect(w.offerKeepDecks).toBe(false);
  });

  it("reports but no deck to download: deleted outright, the reports named", () => {
    const w = studyDeleteWarning({ ...none, without_deck: ["Draft B", "Draft A"] }, "Brändi");
    expect(w.outright).toBe(true);
    expect(w.paragraphs[0]).toMatch(/deleted completely, .* its 2 reports:$/);
    expect(w.lost).toEqual(["Draft A", "Draft B"]);
    expect(w.confirm).toBe("Delete study");
  });

  it("decks kept: archived read-only, not deleted", () => {
    const w = studyDeleteWarning({ ...none, with_deck: ["Delivered"], without_deck: ["Draft"] }, "Brändi");
    expect(w.outright).toBe(false);
    expect(w.paragraphs[0]).toMatch(/read-only for good/);
    expect(w.paragraphs[1]).toBe("The data imported into “Brändi” is deleted.");
    expect(w.lost).toEqual(["Draft"]);
    expect(w.offerKeepDecks).toBe(true);
    expect(w.confirm).toBe("Delete study");
  });

  it("decks unticked: nothing left to download, so deleted outright", () => {
    const w = studyDeleteWarning({ ...none, with_deck: ["Delivered"] }, "Brändi", false);
    expect(w.outright).toBe(true);
    expect(w.paragraphs[0]).toMatch(/its report, generated decks included:$/);
    expect(w.lost).toEqual(["Delivered"]);
    expect(w.offerKeepDecks).toBe(true); // the tick box stays, to change one's mind
    expect(w.confirm).toBe("Delete study and every deck");
  });

  it("unknown usage is never an outright delete", () => {
    expect(studyDeleteWarning(null, "Brändi").outright).toBe(false);
  });
});
