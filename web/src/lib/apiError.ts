/**
 * Turning a refused response into one sentence an author can act on.
 *
 * The server writes `detail` FOR the person who made the request — which file
 * it could not read, what to check. The dialogs show `error.message` verbatim,
 * so anything wrapped around that sentence is noise in front of it: an upload
 * of a corrupt .sav used to read
 * `422 Unprocessable Entity: {"detail":"notes.sav could not be read…"}`.
 *
 * Without a `detail` there is nothing written for a person, and the status line
 * is kept — it is at least something to quote to support.
 */
export function errorMessage(status: number, statusText: string, body: string): string {
  const fallback = `${status} ${statusText}: ${body}`;
  try {
    const detail = (JSON.parse(body) as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    // FastAPI's validation errors are a list of {loc, msg}; the messages are
    // the readable half, and joining them beats printing "[object Object]".
    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => (d && typeof d === "object" ? (d as { msg?: unknown }).msg : null))
        .filter((m): m is string => typeof m === "string" && m.trim() !== "");
      if (msgs.length) return msgs.join("; ");
    }
  } catch {
    // Not JSON — an nginx page, a gateway's own words. Keep the status line.
  }
  return fallback;
}
