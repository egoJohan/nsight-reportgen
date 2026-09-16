/** The queue remembers what each slide's render said about itself.
 *
 *  Two facts, one entry. A slide's picture is blank, or its bars came out too
 *  thin to carry numbers — and the picture can no longer say either for itself:
 *  "No data to show" was English text on a slide handed to a client, and a
 *  chart with no numbers never explained why. Both are told to the author in
 *  the editor, on the same warning button and slide-item icon as every other
 *  slide problem.
 *
 *  Cleared with the rest of the session, and a slide that comes back clean
 *  clears its own note — a warning that outlives the thing it warns about is
 *  worse than none. (Johan, 2026-09-16)
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as q from "./previewQueue";

const CLEAN = { empty: false, unlabelled: 0 };

beforeEach(() => {
  q.__resetForTest();
  q.reset("r1");
});

describe("what a render said about itself", () => {
  it("says nothing about a slide nobody has drawn", () => {
    expect(q.chartFactsOf("s1")).toEqual(CLEAN);
  });

  it("remembers a blank slide", () => {
    q.noteChartFacts("s1", { empty: true, unlabelled: 0 });
    expect(q.chartFactsOf("s1").empty).toBe(true);
  });

  it("remembers how many categories went unlabelled", () => {
    q.noteChartFacts("s1", { empty: false, unlabelled: 25 });
    expect(q.chartFactsOf("s1").unlabelled).toBe(25);
  });

  it("forgets when the slide comes back clean", () => {
    q.noteChartFacts("s1", { empty: true, unlabelled: 25 });
    q.noteChartFacts("s1", CLEAN);
    expect(q.chartFactsOf("s1")).toEqual(CLEAN);
  });

  it("is per slide", () => {
    q.noteChartFacts("s1", { empty: true, unlabelled: 0 });
    expect(q.chartFactsOf("s2")).toEqual(CLEAN);
  });

  it("does not survive the editing session", () => {
    q.noteChartFacts("s1", { empty: true, unlabelled: 0 });
    q.reset("r2");
    expect(q.chartFactsOf("s1")).toEqual(CLEAN);
  });

  it("hands back the same object while nothing changes", () => {
    // useSyncExternalStore compares snapshots by IDENTITY. A fresh object per
    // read re-renders the slide list for ever — which is how this hook would
    // fail, silently and expensively, if anyone 'simplified' it.
    expect(q.chartFactsOf("s1")).toBe(q.chartFactsOf("s2"));
    q.noteChartFacts("s1", { empty: true, unlabelled: 0 });
    expect(q.chartFactsOf("s1")).toBe(q.chartFactsOf("s1"));
  });

  it("does not wake its subscribers when nothing changed", () => {
    const seen = vi.fn();
    q.subscribe(seen);
    q.noteChartFacts("s1", { empty: true, unlabelled: 0 });
    const after = seen.mock.calls.length;
    q.noteChartFacts("s1", { empty: true, unlabelled: 0 });
    expect(seen.mock.calls.length).toBe(after);
  });
});
