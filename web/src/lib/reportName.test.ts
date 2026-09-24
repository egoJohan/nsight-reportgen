import { describe, expect, it } from "vitest";

import { caseListIsStale } from "./reportName";

/**
 * "Kun Studyn jonkin tehdyn raportin nimeä editoi, raportin nimi ei vaihdu
 * pysyvästi vaikka sen vahvistaa tick-painikkeella. Raportti saattaa tulla
 * näkyviin vanhalla nimellä." (2026-09-24)
 *
 * The study's list of reports comes from the server and is cached. A save that
 * renames a report used to leave that cache alone, so going back to the study
 * showed the old name. After a save the list is reloaded exactly when it would
 * show the report under a name other than the one just saved — only then,
 * because the list costs the server a read per report.
 */
describe("caseListIsStale", () => {
  const list = {
    reports: [
      { report_id: "rep-a", name: "Kevät 2026" },
      { report_id: "rep-b", name: "Syksy" },
    ],
  };

  it("is stale when the list shows the report under its old name", () => {
    expect(caseListIsStale(list, "rep-a", "Kevät 2026 — lopullinen")).toBe(true);
  });

  it("is not stale when the name did not change", () => {
    expect(caseListIsStale(list, "rep-a", "Kevät 2026")).toBe(false);
  });

  it("is stale when the list does not know the report yet", () => {
    expect(caseListIsStale(list, "rep-new", "Uusi")).toBe(true);
  });

  it("has nothing to refresh when no list has been loaded", () => {
    expect(caseListIsStale(undefined, "rep-a", "Mikä tahansa")).toBe(false);
  });
});
