import { useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
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

/** Google/Microsoft lead (spec §4, Part B — Tasks 10-14); password sits
 *  below, quieter, but is the only method that actually works until then.
 *
 *  Part B's seam: delete `disabled` and give this an `onClick` that does a
 *  real navigation — `location.assign(`${API_BASE}/auth/${provider}`)` —
 *  once GET /auth/google and /auth/microsoft exist server-side. A `<button>`
 *  on purpose, not an `<a href>`: OIDC needs a fresh navigation each click
 *  (no bfcache reuse of a stale redirect), which `location.assign` gives it
 *  same as a link would, without a dead href sitting in the DOM meanwhile.
 */
function ProviderButton({ label }: { label: string }) {
  return (
    <Button type="button" variant="outline" className="w-full" disabled>
      {label}
    </Button>
  );
}

export default function LoginPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params] = useSearchParams();
  const next = params.get("next") || "/";

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

        <div className="space-y-4 rounded-xl border bg-surface p-6 shadow-sm">
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

          {/* SSO leads. Both disabled until Part B — see ProviderButton. */}
          <div className="space-y-2">
            <ProviderButton label="Continue with Google" />
            <ProviderButton label="Continue with Microsoft" />
            <p className="text-center text-xs text-muted-foreground">
              Google and Microsoft sign-in are not configured yet.
            </p>
          </div>

          <div className="relative">
            <div className="absolute inset-0 flex items-center">
              <span className="w-full border-t" />
            </div>
            <div className="relative flex justify-center">
              <span className="bg-surface px-2 text-xs text-muted-foreground">or</span>
            </div>
          </div>

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
