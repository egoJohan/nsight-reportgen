/** What a failed lock request actually means.
 *
 * The editor closes itself when somebody else has the report — that is the
 * agreed behaviour, and it is right. What it must never do is close on a
 * dropped wifi packet: the editor treated EVERY failure as "somebody else took
 * it", so one failed request during a lock renewal shut the editor and threw
 * away whatever was on screen and not yet written.
 *
 * Only a 409 is evidence that someone else holds it. Everything else — a
 * network error, a 500, a proxy timeout — is an absence of evidence, and the
 * answer to that is to try again, not to discard the author's work.
 */
import { ApiError } from "./api";

export type LockFailure =
  /** The server says another person holds this report. */
  | "taken"
  /** This report is not ours to edit any more — deleted, or our access
   *  revoked. Also a reason to close, with a different thing to say. */
  | "gone"
  /** We could not find out. Keep the report open and keep asking. */
  | "unreachable";

export function classifyLockFailure(e: unknown): LockFailure {
  if (!(e instanceof ApiError)) return "unreachable";
  if (e.status === 409) return "taken";
  // 404: the case or report is gone, or was never visible to us. 403: the
  // grant that let us edit it has been taken away. Treating these as "we could
  // not find out" left the author editing a report that no longer exists —
  // renewing every thirty seconds for ever, with a failed-save toast each time
  // and nothing ever saying why. Before this classifier existed, the editor
  // closed and said so; it has to keep doing that.
  if (e.status === 404 || e.status === 403) return "gone";
  return "unreachable";
}

/** What to tell the author when a lock failure means the editor must close. */
export function lockFailureMessage(kind: LockFailure, fallback: string): string {
  if (kind === "gone") {
    return "This report is no longer available to you — it may have been " +
      "deleted, or your access to it changed.";
  }
  return fallback;
}
