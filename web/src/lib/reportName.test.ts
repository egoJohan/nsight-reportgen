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

/**
 * Still reverting, 2026-09-25: the editor started from the CACHED report, and
 * after a save that cache still held the old document (only marked stale). So
 * reopening a just-renamed report showed the old name, and its next autosave
 * wrote the old name back to the server.
 */
describe("after a save, the cached report is what was saved", () => {
  it("holds the new name, not the one it was opened with", async () => {
    const { QueryClient } = await import("@tanstack/react-query");
    const { qk } = await import("./queries");
    const { rememberSavedReport } = await import("./reportName");
    const qc = new QueryClient();
    const key = qk.report("case-1", "rep-a");
    qc.setQueryData(key, { name: "Kevät 2026", charts: [], template_ref: "t" });

    rememberSavedReport(qc, "case-1", "rep-a", {
      name: "Kevät 2026 — lopullinen", charts: [], template_ref: "t",
    } as never);

    expect(qc.getQueryData<{ name: string }>(key)?.name).toBe("Kevät 2026 — lopullinen");
  });
});

describe("mayStartEditing", () => {
  it("never starts from a copy fetched before this visit", async () => {
    const { mayStartEditing } = await import("./reportName");
    expect(mayStartEditing({ hasDraft: false, loaded: true, fetchedThisVisit: false })).toBe(false);
  });

  it("starts from the server's copy fetched on opening", async () => {
    const { mayStartEditing } = await import("./reportName");
    expect(mayStartEditing({ hasDraft: false, loaded: true, fetchedThisVisit: true })).toBe(true);
  });

  it("never re-seeds a draft already being edited", async () => {
    const { mayStartEditing } = await import("./reportName");
    expect(mayStartEditing({ hasDraft: true, loaded: true, fetchedThisVisit: true })).toBe(false);
  });
});
