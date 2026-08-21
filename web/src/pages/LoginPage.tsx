import { type ReactNode, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import TiledBackdrop from "@/components/layout/TiledBackdrop";
import type { Me } from "@/lib/session";

// Relative by default (spec §5.4), matching api.ts / session.ts: same-origin
// is what makes the SameSite=Strict session cookie work at all.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

// Both /auth/login/password and /auth/register are deliberately
// non-revealing on the server (a wrong password and an unknown email get the
// same 401; "already exists" and "domain not allowed" get the same 403) so
// neither can be used to discover whether an account exists. Repeating that
// distinction in the UI — "no account with that email" vs "wrong password" —
// would rebuild the oracle the server went out of its way to remove, so both
// copy strings below say only what the server's status code actually proves.
const LOGIN_FAILED = "Those details did not match.";
const REGISTER_REFUSED = "Registration is not available for that email.";
const UNREACHABLE = "Could not reach the server. Try again.";

type Mode = "signin" | "register";

/** Where an SSO click actually goes. A plain `<a href>`, not `onClick` +
 *  `location.assign`: this has to be a real top-level browser navigation so
 *  the 302 from `/auth/login/{provider}` is followed by the browser itself
 *  — a `fetch` cannot follow a cross-origin redirect into a consent screen,
 *  it just fails opaque-CORS. `next` rides along as a query param; the
 *  backend stashes it in the `nsight_oauth` state cookie (routes_auth.py)
 *  so it survives the round trip to the provider and back, and is read back
 *  out of that cookie — not the URL — when the callback redirects into the
 *  app on success.
 */
const providerLoginUrl = (provider: "google" | "microsoft", next: string): string =>
  `${API_BASE}/auth/login/${provider}?next=${encodeURIComponent(next)}`;

/** Which of the two providers are actually configured (`PUT /settings/oidc`)
 *  — this page is signed-out, so it cannot call that route (admin-only); it
 *  calls `GET /auth/providers` instead, a deliberately public sibling that
 *  reports the same presence flags and nothing else (no client id, no
 *  secret). Until it resolves, both buttons stay hidden rather than risking
 *  a flash of a button that 503s on click.
 */
interface ProviderAvailability {
  google: boolean;
  microsoft: boolean;
}

function useProviderAvailability() {
  return useQuery<ProviderAvailability>({
    queryKey: ["auth", "providers"],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/auth/providers`);
      if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
      return res.json();
    },
    staleTime: 60_000,
  });
}

/** The callback (routes_auth.py `oidc_callback`) never mints a session on
 *  refusal — it redirects here with `?error=…` instead, so this is the only
 *  place that refusal is ever shown. `not_allowed` is spec §4 step 3: a real
 *  identity, an email nSight does not admit. `sign_in_failed` covers
 *  everything upstream of that check (a rejected/expired code, a bad token)
 *  — deliberately vaguer, since the server's own log line is where the real
 *  reason lives (never sent to the browser).
 */
const SSO_ERROR_MESSAGES: Record<string, string> = {
  not_allowed: "That email isn't set up for nSight Studio. Ask an admin to add it, then try again.",
  sign_in_failed: "That sign-in didn't go through. Try again, or use your password below.",
};

/** The providers' own marks, inline.
 *
 *  Inline SVG rather than a file or a CDN: these sit on the one screen a
 *  signed-out visitor can reach, so they must render before anything else
 *  loads and without a second request. Both are the vendors' published
 *  brand geometry — Google's four-colour G and Microsoft's four squares —
 *  which their brand guidelines require be used unaltered in colour and
 *  proportion, so neither takes `currentColor` the way our own icons do.
 */
function GoogleMark() {
  return (
    <svg viewBox="0 0 18 18" aria-hidden className="size-4 shrink-0">
      <path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.91c1.7-1.57 2.69-3.88 2.69-6.62z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.81.54-1.84.86-3.05.86-2.34 0-4.33-1.58-5.04-3.71H.96v2.33A9 9 0 0 0 9 18z" />
      <path fill="#FBBC05" d="M3.96 10.71a5.41 5.41 0 0 1 0-3.42V4.96H.96a9 9 0 0 0 0 8.08l3-2.33z" />
      <path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.96l3 2.33C4.67 5.16 6.66 3.58 9 3.58z" />
    </svg>
  );
}

function MicrosoftMark() {
  return (
    <svg viewBox="0 0 18 18" aria-hidden className="size-4 shrink-0">
      <path fill="#F25022" d="M0 0h8.5v8.5H0z" />
      <path fill="#7FBA00" d="M9.5 0H18v8.5H9.5z" />
      <path fill="#00A4EF" d="M0 9.5h8.5V18H0z" />
      <path fill="#FFB900" d="M9.5 9.5H18V18H9.5z" />
    </svg>
  );
}

function ProviderButton({ label, mark, href }: { label: string; mark: ReactNode; href: string }) {
  return (
    // `block`, not the anchor's default `inline`: space-y-* spaces siblings with
    // margin-top, and margin-top does nothing on an inline element — so without
    // this the two buttons sit flush against each other no matter what spacing
    // the parent asks for.
    <a href={href} className="block">
      <Button type="button" variant="outline" className="w-full justify-center gap-2">
        {mark}
        {label}
      </Button>
    </a>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";
  const ssoErrorCode = params.get("error");
  const ssoError = ssoErrorCode
    ? (SSO_ERROR_MESSAGES[ssoErrorCode] ?? "Sign-in didn't complete. Try again.")
    : null;
  const { data: providers, isPending: providersPending } = useProviderAvailability();
  const showGoogle = providers?.google ?? false;
  const showMicrosoft = providers?.microsoft ?? false;

  const [mode, setMode] = useState<Mode>("signin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function switchMode(m: Mode) {
    setMode(m);
    setError(null);
    // A password typed for one mode has no business surviving into the
    // other — clear it along with the error rather than carry it across.
    setPassword("");
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const path = mode === "signin" ? "/auth/login/password" : "/auth/register";
    try {
      const res = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!res.ok) {
        setError(mode === "signin" ? LOGIN_FAILED : REGISTER_REFUSED);
        // The failed password never needs to be typed again for the same
        // email — and it should not go on sitting in state while the person
        // reads the error and decides what to do next.
        setPassword("");
        return;
      }
      // useSession's ["auth","me"] query is still cached from whatever got
      // us onto this page (often a 401 -> null, from AppShell's own guard).
      // Without this, that stale `null` outlives the new cookie for up to
      // staleTime, and AppShell reads it before its next refetch — bouncing
      // straight back to /login the instant we navigate to `next`. Seeding
      // the cache with the response body — which is the same {id, email,
      // name, is_admin} shape /auth/me returns — makes the new session
      // visible immediately instead of on a timer.
      const me: Me = await res.json();
      queryClient.setQueryData(["auth", "me"], me);
      navigate(next, { replace: true });
    } catch {
      setError(UNREACHABLE);
      setPassword("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative isolate flex min-h-screen items-center justify-center bg-background px-4">
      {/* Stronger than the app default (0.13): here it's the only thing on
          the page behind one small card, not competing with a table or a
          chart, so it can carry real weight. */}
      <TiledBackdrop opacity={0.3} />

      <div className="w-full max-w-sm">
        {/* The mark is white, so it sits on a dark brand band — same
            treatment as the sidebar header, the one other place it appears. */}
        <div className="mx-auto mb-6 flex w-fit items-center justify-center rounded-xl bg-primary px-6 py-4">
          <img src="/nsight-logo.svg" alt="nSight" className="h-10 w-auto" />
        </div>

        {/* shadow-xl, not the shadow-sm a panel gets on a working page: this card
          sits over a deliberately strong tiled backdrop, and a faint shadow
          reads as a flat patch rather than something lifted off it. */}
      <div className="space-y-4 rounded-xl border bg-surface p-6 shadow-xl shadow-black/10 dark:shadow-black/40">
          <div>
            <h1 className="text-lg font-semibold tracking-tight">
              {mode === "signin" ? "Sign in to nSight Studio" : "Create an account"}
            </h1>
            <p className="mt-1 text-sm text-muted-foreground">
              {mode === "signin"
                ? "Use your work email to continue."
                : "Available for allowed organisation domains."}
            </p>
          </div>

          {ssoError && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {ssoError}
            </p>
          )}

          {/* Only offer a provider GET /auth/providers reports configured —
              see useProviderAvailability. Hidden entirely, divider included,
              when neither is.

              While the check is in flight we render the block INVISIBLE rather
              than absent: it still occupies its full height, so the card does
              not grow under the cursor when the answer arrives. Omitting it
              made the login screen visibly resize a moment after paint. */}
          {(showGoogle || showMicrosoft || providersPending) && (
            <div className={providersPending ? "invisible" : undefined} aria-hidden={providersPending}>
              <div className="space-y-3">
                {(showGoogle || providersPending) && (
                  <ProviderButton
                    label="Continue with Google"
                    mark={<GoogleMark />}
                    href={providerLoginUrl("google", next)}
                  />
                )}
                {(showMicrosoft || providersPending) && (
                  <ProviderButton
                    label="Continue with Microsoft"
                    mark={<MicrosoftMark />}
                    href={providerLoginUrl("microsoft", next)}
                  />
                )}
              </div>

              <div className="relative mt-4">
                <div className="absolute inset-0 flex items-center">
                  <span className="w-full border-t" />
                </div>
                <div className="relative flex justify-center">
                  <span className="bg-surface px-2 text-xs text-muted-foreground">or</span>
                </div>
              </div>
            </div>
          )}

          <form onSubmit={submit} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                required
                autoFocus
                autoComplete="username"
                value={email}
                placeholder="you@company.com"
                disabled={busy}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                required
                minLength={mode === "register" ? 12 : undefined}
                autoComplete={mode === "signin" ? "current-password" : "new-password"}
                value={password}
                placeholder="Password"
                disabled={busy}
                onChange={(e) => setPassword(e.target.value)}
              />
              {mode === "register" && (
                <p className="text-xs text-muted-foreground">At least 12 characters.</p>
              )}
            </div>

            {error && (
              <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
                {error}
              </p>
            )}

            <Button type="submit" disabled={busy} className="w-full">
              {busy
                ? mode === "signin"
                  ? "Signing in…"
                  : "Creating account…"
                : mode === "signin"
                  ? "Sign in"
                  : "Create account"}
            </Button>

            <p className="text-center text-sm text-muted-foreground">
              {mode === "signin" ? (
                <>
                  New here?{" "}
                  <button
                    type="button"
                    onClick={() => switchMode("register")}
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    Create an account
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{" "}
                  <button
                    type="button"
                    onClick={() => switchMode("signin")}
                    className="text-primary underline-offset-4 hover:underline"
                  >
                    Sign in
                  </button>
                </>
              )}
            </p>
          </form>
        </div>
      </div>
    </div>
  );
}
