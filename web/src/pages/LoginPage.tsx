import { type ReactNode } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import TiledBackdrop from "@/components/layout/TiledBackdrop";

// Relative by default (spec §5.4), matching api.ts / session.ts: same-origin
// is what makes the SameSite=Strict session cookie work at all.
const API_BASE = import.meta.env.VITE_API_BASE ?? "";

// There is no password and no self-service account. An admin invites you,
// which creates your account and its access there and then; signing in proves
// you are the person that address belongs to, and only Google and Microsoft
// can prove that. The page therefore offers exactly two buttons and no form —
// an email box with nothing behind it would invite people to try, and the only
// honest answer to most of them would be a refusal.

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
  sign_in_failed: "That sign-in didn't go through. Try again.",
  sign_in_cancelled: "Sign-in was cancelled. Try again when you're ready.",
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
  const [params] = useSearchParams();
  const next = params.get("next") || "/";
  const ssoErrorCode = params.get("error");
  const ssoError = ssoErrorCode
    ? (SSO_ERROR_MESSAGES[ssoErrorCode] ?? "Sign-in didn't complete. Try again.")
    : null;
  const { data: providers, isPending: providersPending } = useProviderAvailability();
  const showGoogle = providers?.google ?? false;
  const showMicrosoft = providers?.microsoft ?? false;
  const noneConfigured = !providersPending && !showGoogle && !showMicrosoft;

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
        {/* Centred throughout: the logo, the heading and the two provider
            buttons are one vertical stack, and a left-aligned heading over
            centred buttons read as two different layouts sharing a card.
            Matches RequestAccessPage, which is the same card at the next
            step. */}
        <div className="space-y-4 rounded-xl border bg-surface p-6 text-center shadow-xl shadow-black/10 dark:shadow-black/40">
          <h1 className="text-lg font-semibold tracking-tight">
            Sign in to nSight Studio
          </h1>

          {ssoError && (
            <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
              {ssoError}
            </p>
          )}

          {/* Only offer a provider GET /auth/providers reports configured —
              see useProviderAvailability.

              While the check is in flight the block is INVISIBLE rather than
              absent: it still occupies its full height, so the card does not
              grow under the cursor when the answer arrives. Omitting it made
              the login screen visibly resize a moment after paint. */}
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
          </div>

          {/* Neither provider configured means nobody can sign in at all. Say
              so plainly: without this the card is an empty box, which reads as
              a page that failed to load rather than a hive that needs
              setting up. */}
          {noneConfigured && (
            <p className="rounded-lg border bg-muted/30 p-3 text-sm text-muted-foreground">
              No sign-in provider is configured yet. An administrator needs to
              set up Google or Microsoft sign-in before anyone can get in.
            </p>
          )}

          <p className="text-xs text-muted-foreground">
            No account yet? Sign in anyway to request it.
          </p>
        </div>
      </div>
    </div>
  );
}
