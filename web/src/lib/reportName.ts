import type { QueryClient } from "@tanstack/react-query";

import type { ReportDoc } from "./api";
import { qk } from "./queries";

/** Whether the study's cached list of reports would show `reportId` under a
 *  name other than `name` — the one just saved. Then the list is reloaded;
 *  otherwise it is left alone, because it costs the server a read per report.
 *
 *  "Raportin nimi ei vaihdu pysyvästi vaikka sen vahvistaa tick-painikkeella":
 *  a save that renamed a report left the list's cache as it was, so the study
 *  page went on showing the old name. (2026-09-24)
 *
 *  No list loaded means nothing is showing a name, so nothing is stale — the
 *  list fetches the server's copy when it is first wanted. */
export function caseListIsStale(
  list: { reports: { report_id: string; name: string }[] } | undefined,
  reportId: string,
  name: string,
): boolean {
  if (!list) return false;
  const shown = list.reports.find((r) => r.report_id === reportId);
  return !shown || shown.name !== name;
}


/** Put what was just saved into the cached report, so the cache holds what
 *  the server now holds.
 *
 *  It used to be only marked stale, keeping the OLD document. The editor opened
 *  from that cache, so reopening a just-renamed report showed its old name, and
 *  the next autosave wrote the old name — and any older content — back to the
 *  server: "raportin nimi ei vaihdu pysyvästi" was still happening after the
 *  list fix (2026-09-25). */
export function rememberSavedReport(
  qc: QueryClient,
  caseId: string,
  reportId: string,
  report: ReportDoc,
): void {
  qc.setQueryData<ReportDoc>(qk.report(caseId, reportId),
    (old) => (old ? { ...old, ...report } : report));
}

/** Whether the editor may start its working draft from `loaded`: only from a
 *  copy fetched when this visit opened the report, and only once.
 *
 *  Never from a cached copy. Whatever put it there — an earlier visit, another
 *  tab, a colleague saving since — it can be older than the server's, and
 *  whatever the editor starts from is what its next save writes back. */
export function mayStartEditing(s: {
  hasDraft: boolean;
  loaded: boolean;
  fetchedThisVisit: boolean;
}): boolean {
  return !s.hasDraft && s.loaded && s.fetchedThisVisit;
}
