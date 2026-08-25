/**
 * What the no-access page may honestly say.
 *
 * The page renders only when the customer 404s — when the viewer holds no
 * grant on it RIGHT NOW. Everything on it has to be true given that, and the
 * first version was not: it read an access request in state "granted" as a
 * statement about current access and printed "Access granted." beneath a
 * paragraph saying the opposite, with a Continue button that returned to the
 * same page because nothing had changed.
 *
 * A request row records a DECISION, once. The grant itself is written
 * separately (`repository.decide_access_request` — "does NOT itself touch
 * grants") and can be changed afterwards in the permissions dialog. So
 * "granted" is history. If it is history AND the customer still 404s, the
 * access was removed after it was given — or, benignly, it was given seconds
 * ago and this tab is still holding the 404. Both are worth a re-check;
 * neither is worth announcing as access.
 */
export interface AccessNotice {
  /** The paragraph under the customer name. */
  lead: string;
  /** Offer "Request access". */
  showRequest: boolean;
  /** Offer "Check again" — only where a stale 404 is plausible. */
  showRecheck: boolean;
  /** A smaller line of context, when there is one. */
  note?: string;
}

export function accessNoticeFor(state: string | undefined | null): AccessNotice {
  if (state === "pending") {
    return {
      lead: "Your request is waiting for an admin to review it.",
      showRequest: false,
      showRecheck: true,
    };
  }
  if (state === "granted") {
    return {
      lead:
        "This access was granted before but is no longer in force — it may " +
        "have been changed since. If it was just granted, check again.",
      showRequest: true,
      showRecheck: true,
    };
  }
  if (state === "refused") {
    return {
      lead: "You don’t have access to this customer yet.",
      showRequest: true,
      showRecheck: false,
      note: "A previous request was refused. You can ask again.",
    };
  }
  // Unknown states included: an unrecognised value tells us nothing, so treat
  // the viewer as someone who has not asked yet rather than inventing a status.
  return {
    lead:
      "You don’t have access to this customer yet. Request view or edit " +
      "access and an admin will review it.",
    showRequest: true,
    showRecheck: false,
  };
}
