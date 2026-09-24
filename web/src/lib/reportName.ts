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
