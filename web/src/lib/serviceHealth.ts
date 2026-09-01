/** Whether the backend/hive can serve right now, and who wants to know.
 *
 *  nSight stores nothing itself — every case, report and material lives in the
 *  hive — so while the hive is upgrading or down, almost every request fails.
 *  The browser used to learn that one request at a time, which showed as a
 *  broken page or a queue of identical error toasts.
 *
 *  This is deliberately a tiny store rather than React state: the thing that
 *  DETECTS the outage is `json()` in api.ts, which is called from plain
 *  functions with no component context, and the thing that DISPLAYS it is a
 *  component. A module-level subscription is what lets those two meet without
 *  threading a context through every call site.
 */
/** What went wrong, which decides which screen the user sees.
 *
 *  `maintenance` — 502/503/504, or a request that never landed: the data
 *  service is away, most likely an upgrade or a restart. It comes back on its
 *  own, so the screen says so and clears itself.
 *  `error` — 500 and anything else in the 5xx range: something broke that
 *  waiting will not fix, so the screen says that instead of promising a
 *  recovery that may never come.
 */
export type Outage = "maintenance" | "error";

const listeners = new Set<() => void>();
let down: Outage | null = null;
/** The request that failed. Shown on the maintenance screen and retried by its
 *  button, so "try again" means the thing that actually broke rather than a
 *  blind page reload. */
let failedPath = "";

/** The current outage kind, or null when the app believes it is healthy. */
export function outage(): Outage | null {
  return down;
}

function set(next: Outage | null) {
  if (next === down) return;
  down = next;
  listeners.forEach((l) => l());
}

/** Called by the API layer when a request fails in a way that means "the
 *  service, not this request": a 502/503/504, or a fetch that never landed.
 *  A 404 or a 409 is about the thing you asked for and must NOT raise this. */
export function reportUnreachable(url?: string, kind: Outage = "maintenance"): void {
  if (url) {
    try {
      // Path only: the origin is noise to a reader, and a full URL can carry a
      // session cookie's worth of query string into the UI.
      failedPath = new URL(url, location.origin).pathname;
    } catch {
      failedPath = url;
    }
  }
  set(kind);
}

/** The path of the request that raised the screen, for display and retry. */
export function lastFailedPath(): string {
  return failedPath;
}

/** Called when something succeeds, or the readiness probe says we are back. */
export function reportReachable(): void {
  set(null);
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** Ask the server whether it can serve. Unauthenticated, and cached server-side,
 *  so polling it while the screen is up cannot add load to a sick hive. */
export async function probeReady(): Promise<boolean> {
  try {
    const res = await fetch(`${import.meta.env.VITE_API_BASE ?? ""}/readyz`, {
      cache: "no-store",
    });
    if (!res.ok) return false;
    const body = (await res.json()) as { ok?: boolean };
    return body?.ok === true;
  } catch {
    return false;
  }
}


/** Watch every request the app makes, from one place.
 *
 *  Detection used to live in `json()` in api.ts, which most calls pass
 *  through — but not all: `useSession` fetches `/auth/me` with a raw fetch and
 *  its own error handling, so the very first request of a cold page load could
 *  fail with 503 and raise nothing. Anything that misses the outage detector is
 *  invisible to it, and the call sites are too many to keep in step by hand.
 *
 *  This only OBSERVES: it forwards the call untouched and never alters a
 *  response, a status, or an error.
 */
export function installFetchProbe(): void {
  if (typeof window === "undefined") return;
  const original = window.fetch.bind(window);

  const watched = (url: string): boolean => {
    try {
      const u = new URL(url, location.origin);
      // Same-origin only, and never the readiness probe itself — it answers
      // 503 BY DESIGN while things are down, and would keep re-raising the
      // screen it exists to take away.
      return u.origin === location.origin && u.pathname !== "/readyz";
    } catch {
      return false;
    }
  };

  window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.href
          : input.url;
    try {
      const res = await original(input as RequestInfo, init);
      if (watched(url)) {
        if (res.status >= 500) {
          // 503/502/504 are "the service is away, come back" — an upgrade, a
          // restart. A 500 is "something broke", which waiting does not fix,
          // and telling the user to wait for it would be a false promise.
          reportUnreachable(res.url || url,
                            res.status === 500 ? "error" : "maintenance");
        } else if (res.ok) {
          reportReachable();
        }
      }
      return res;
    } catch (err) {
      // The request never landed: the backend is not listening, or the network
      // went away. Indistinguishable from the user's point of view.
      if (watched(url)) reportUnreachable(url);
      throw err;
    }
  };
}
