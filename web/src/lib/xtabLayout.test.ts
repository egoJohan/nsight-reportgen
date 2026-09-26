import { describe, expect, it } from "vitest";

import { shownXtabLayout } from "./xtabLayout";

const OFFERED = ["grouped", "small_multiples", "small_multiples_grid", "separate"];
const counts: Record<string, number> = { sukupuoli: 4, alue: 5, ika: 2, kylla: 2 };
const n = (name: string | null | undefined) => (name ? counts[name] : undefined);

describe("the layout the selector shows", () => {
  it("shows an explicit choice as it is", () => {
    const chart = { classifying_var: "sukupuoli", classifying_var_2: "alue",
                    options: { xtab_layout: "small_multiples_grid" } };
    expect(shownXtabLayout(chart, OFFERED, n)).toBe("small_multiples_grid");
  });

  it("shows an old 'auto' slide as the one row of panels it draws (4 x 5 = 20)", () => {
    const chart = { classifying_var: "sukupuoli", classifying_var_2: "alue",
                    options: { xtab_layout: "auto" } };
    expect(shownXtabLayout(chart, OFFERED, n)).toBe("small_multiples");
  });

  it("shows grouped bars where the rule groups them (2 x 2 = 4)", () => {
    const chart = { classifying_var: "ika", classifying_var_2: "kylla", options: {} };
    expect(shownXtabLayout(chart, OFFERED, n)).toBe("grouped");
  });

  it("counts only the groups the author kept (2 of 4 x 5 = 10 → panels)", () => {
    const chart = { classifying_var: "sukupuoli", classifying_var_2: "alue",
                    classifying_values: ["Mies", "Nainen"] };
    expect(shownXtabLayout(chart, OFFERED, n)).toBe("small_multiples");
  });

  it("leaves a stacked chart's 'Combined panel' alone", () => {
    const chart = { classifying_var: "sukupuoli", classifying_var_2: "alue", options: {} };
    expect(shownXtabLayout(chart, ["auto", "separate"], n)).toBe("auto");
  });
});
