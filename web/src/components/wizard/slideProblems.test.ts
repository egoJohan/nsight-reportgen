/** What the editor tells an author about a slide.
 *
 *  These warnings carry disclosures that used to be printed on the slide
 *  itself — which groups it left out, which it was narrowed to, that it had
 *  nothing to chart. Five backend tests were REVERSED to assert those lines are
 *  no longer on the deck, on the promise that the editor says it instead.
 *
 *  Nothing tested the editor side. `slideProblems` was not even exported, and a
 *  guard that could never fire shipped and reached staging: it compared the
 *  author's ticked groups against `drawn + thin + capped`, which the server
 *  computes FROM those same ticked groups, so the two could never disagree.
 *
 *  The promise is now a test. (Johan, 2026-09-17)
 */
import { describe, expect, it } from "vitest";
import { renderProblems, slideProblems } from "./StepConfigure";
import type { ChartSpec, PanelSelection } from "@/lib/api";

const CHART = { classifying_var: "sukup", classifying_values: [] } as unknown as ChartSpec;

function panels(over: Partial<PanelSelection> = {}): PanelSelection {
  return {
    drawn: ["Mies", "Nainen"], thin: [], capped: [], degraded: false,
    split: true, max_panels: 3, narrowed_to: [], ...over,
  };
}

const ids = (p: ReturnType<typeof slideProblems>) => p.map((x) => x.id);

describe("narrowed to some groups", () => {
  it("is raised when the engine narrowed the slide", () => {
    expect(ids(slideProblems(CHART, panels({ narrowed_to: ["Mies"] }))))
      .toContain("narrowed-to-groups");
  });

  it("names the groups, because the slide no longer does", () => {
    const [p] = slideProblems(CHART, panels({ narrowed_to: ["Mies", "Muu"] }));
    expect(p.detail).toContain("Mies, Muu");
  });

  it("is silent on a slide covering everybody", () => {
    expect(ids(slideProblems(CHART, panels()))).not.toContain("narrowed-to-groups");
  });

  it("is silent when the slide also draws the Total", () => {
    // A pie's Total panel is the whole study, whichever groups are ticked, so
    // the slide already says it is not only those groups. (2026-09-19)
    expect(ids(slideProblems(CHART, panels({ drawn: ["Total", "Mies"], narrowed_to: ["Mies"] }))))
      .not.toContain("narrowed-to-groups");
  });

  it("is silent when the ticked names resolve to nothing", () => {
    // Stale `classifying_values` left behind by a change of classifying
    // variable. The engine ignores names it cannot resolve and charts the whole
    // sample; the warning must follow the engine, not the spec — reading the
    // spec is what made it announce groups of a variable the slide had stopped
    // using.
    const stale = { ...CHART, classifying_values: ["Design 1", "Design 3"] } as ChartSpec;
    expect(ids(slideProblems(stale, panels({ narrowed_to: [] }))))
      .not.toContain("narrowed-to-groups");
  });
});

describe("the other slide problems", () => {
  it("reports groups too small to chart", () => {
    expect(ids(slideProblems(CHART, panels({ thin: ["Muu"] })))).toContain("thin-groups");
  });

  it("reports a split that could not be drawn", () => {
    expect(ids(slideProblems(CHART, panels({ degraded: true, drawn: ["Total"] }))))
      .toContain("grouping-dropped");
  });

  it("says nothing about a slide with no classifier", () => {
    const plain = { ...CHART, classifying_var: null } as unknown as ChartSpec;
    expect(slideProblems(plain, panels())).toEqual([]);
  });

  it("says nothing before the answer has arrived", () => {
    expect(slideProblems(CHART, undefined)).toEqual([]);
  });
});

describe("what the picture could not say for itself", () => {
  it("reports a blank slide", () => {
    expect(ids(renderProblems({ empty: true, unlabelled: 0 }))).toEqual(["no-data"]);
  });

  it("reports a chart too dense to label, with the count", () => {
    const [p] = renderProblems({ empty: false, unlabelled: 25 });
    expect(p.id).toBe("unlabelled");
    expect(p.title).toContain("25");
  });

  it("is silent on an ordinary chart", () => {
    expect(renderProblems({ empty: false, unlabelled: 0 })).toEqual([]);
  });
});

describe("small groups (drawn since 2026-09-17)", () => {
  it("names each small group with its size", () => {
    const problems = slideProblems(CHART, panels({
      drawn: ["Amazon", "Walmart"], thin: ["Amazon", "Walmart"],
      sizes: { Amazon: 3, Walmart: 6 },
    }));
    const thin = problems.find((p) => p.id === "thin-groups")!;
    expect(thin.title).toBe("2 small groups");
    expect(thin.detail).toContain("Amazon (n=3), Walmart (n=6)");
    expect(thin.detail).toContain("They are drawn");
  });
});
