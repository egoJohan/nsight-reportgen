import { describe, expect, it } from "vitest";

import { studyNameFrom } from "./studyName";

/**
 * A study is named from the file it was made of. The SAV's own study label is
 * the better name when it has one — it is what the researcher typed — and the
 * file name is the fallback that always exists.
 */
describe("studyNameFrom", () => {
  it("uses the file name without its extension", () => {
    expect(studyNameFrom("Attendo 2026.sav", null)).toBe("Attendo 2026");
  });

  it("prefers the study label the SAV carries", () => {
    expect(studyNameFrom("q4_final_v3.sav", "Hoivapalvelut 2026")).toBe(
      "Hoivapalvelut 2026"
    );
  });

  it("strips the extension whatever its case, and .zsav too", () => {
    expect(studyNameFrom("Study.SAV", null)).toBe("Study");
    expect(studyNameFrom("Study.ZSAV", null)).toBe("Study");
    expect(studyNameFrom("Study.zsav", null)).toBe("Study");
  });

  it("keeps dots inside the name", () => {
    // Only the trailing extension goes; "v1.2" is part of what it is called.
    expect(studyNameFrom("Attendo v1.2.sav", null)).toBe("Attendo v1.2");
  });

  it("ignores a blank or whitespace label", () => {
    expect(studyNameFrom("Attendo.sav", "")).toBe("Attendo");
    expect(studyNameFrom("Attendo.sav", "   ")).toBe("Attendo");
  });

  it("trims a label that is otherwise good", () => {
    expect(studyNameFrom("x.sav", "  Hoiva 2026  ")).toBe("Hoiva 2026");
  });

  it("ignores a label that just repeats the file name", () => {
    // SPSS files often carry the export's own file name as the label; that is
    // not extra information, and re-using it would look like a rename happened.
    expect(studyNameFrom("Attendo 2026.sav", "Attendo 2026")).toBe("Attendo 2026");
    expect(studyNameFrom("Attendo 2026.sav", "Attendo 2026.sav")).toBe("Attendo 2026");
  });

  it("falls back to something usable when the name is only an extension", () => {
    expect(studyNameFrom(".sav", null)).toBe("Untitled study");
    expect(studyNameFrom("", null)).toBe("Untitled study");
  });
});
