import { describe, expect, it } from "vitest";

import { accessNoticeFor } from "./accessNotice";

/**
 * This page only ever renders when the customer 404s — that is, when the
 * viewer has NO access right now. Everything it says has to be true given
 * that, which is what the old version got wrong: it read a request row in
 * state "granted" as a statement about current access and announced "Access
 * granted." on a page that exists because access was denied.
 *
 * A request row records a DECISION, once. Grants are set separately (see
 * repository.decide_access_request — "does NOT itself touch grants") and can
 * be changed afterwards in the permissions dialog, so "granted" is history,
 * not status.
 */
describe("accessNoticeFor", () => {
  it("asks a first-time viewer to request access", () => {
    const n = accessNoticeFor(undefined);
    expect(n.lead).toMatch(/don’t have access|don't have access/i);
    expect(n.showRequest).toBe(true);
    expect(n.showRecheck).toBe(false);
  });

  it("tells a waiting viewer to wait, and does not re-offer the request", () => {
    const n = accessNoticeFor("pending");
    expect(n.lead).toMatch(/waiting|review/i);
    expect(n.showRequest).toBe(false);
  });

  it("never claims access is granted on a page that exists because it is not", () => {
    const n = accessNoticeFor("granted");
    expect(n.lead).not.toMatch(/access granted/i);
    // The honest reading: it was granted once and is not in force now.
    expect(n.lead).toMatch(/no longer|removed|not in force|since/i);
  });

  it("lets a previously-granted viewer re-check and ask again", () => {
    // Re-check matters because there IS a benign version of this state: the
    // grant landed seconds ago and this tab still holds the 404.
    const n = accessNoticeFor("granted");
    expect(n.showRecheck).toBe(true);
    expect(n.showRequest).toBe(true);
  });

  it("says a refusal can be appealed", () => {
    const n = accessNoticeFor("refused");
    expect(n.note).toMatch(/refused/i);
    expect(n.showRequest).toBe(true);
  });

  it("treats an unknown state as a first-time viewer rather than guessing", () => {
    expect(accessNoticeFor("something-new")).toEqual(accessNoticeFor(undefined));
  });
});
