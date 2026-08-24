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
  /** We could not find out. Keep the report open and keep asking. */
  | "unreachable";

export function classifyLockFailure(e: unknown): LockFailure {
  return e instanceof ApiError && e.status === 409 ? "taken" : "unreachable";
}
