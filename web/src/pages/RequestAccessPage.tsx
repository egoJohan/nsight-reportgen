/**
 * Where a verified stranger lands.
 *
 * Google or Microsoft has just vouched for this person's address and nSight
 * has no account for it. The sign-in did not fail — their identity is exactly
 * as proven as anyone else's — so this page is not an error page. It is the
 * one place they can do something about it.
 *
 * Four states, and the server tells us which in one call (`signup.me`) rather
 * than leaving the page to infer it from an error code:
 *
 *   no ticket      the fifteen minutes ran out, or they came here directly
 *   has_account    invited while they held the ticket — sign in, don't ask
 *   pending        already asked; an email is coming
 *   otherwise      they can ask
 */
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2Icon, ClockIcon, LockIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import TiledBackdrop from "@/components/layout/TiledBackdrop";
import { api, ApiError } from "@/lib/api";
import { PAGE_TITLE } from "@/lib/surfaces";

function Card({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative isolate flex min-h-screen items-center justify-center bg-background px-4">
      <TiledBackdrop opacity={0.3} />
      <div className="w-full max-w-sm">
        <div className="mx-auto mb-6 flex w-fit items-center justify-center rounded-xl bg-primary px-6 py-4">
          <img src="/nsight-logo.svg" alt="nSight" className="h-10 w-auto" />
        </div>
        <div className="space-y-4 rounded-xl border bg-surface p-6 text-center shadow-xl shadow-black/10 dark:shadow-black/40">
          {children}
        </div>
      </div>
    </div>
  );
}

export default function RequestAccessPage() {
  const qc = useQueryClient();
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: ticket, isPending, isError } = useQuery({
    queryKey: ["signup", "me"],
    queryFn: api.signup.me,
    retry: false,
  });

  if (isPending) {
    return (
      <Card>
        <p className="text-sm text-muted-foreground">One moment&hellip;</p>
      </Card>
    );
  }

  // No readable ticket. Fifteen minutes is deliberately short, so this is a
  // normal thing to hit — say what to do, not what went wrong.
  if (isError || !ticket) {
    return (
      <Card>
        <LockIcon className="mx-auto size-8 text-muted-foreground" />
        <h1 className={PAGE_TITLE}>Sign in first</h1>
        <p className="text-sm text-muted-foreground">
          Sign in with Google or Microsoft, and if you don&rsquo;t have access
          yet you&rsquo;ll be able to request it here.
        </p>
        <Button variant="outline" className="w-full" onClick={() => (window.location.href = "/login")}>
          Go to sign in
        </Button>
      </Card>
    );
  }

  // Invited while they held the ticket. There is nothing to ask for.
  if (ticket.has_account) {
    return (
      <Card>
        <CheckCircle2Icon className="mx-auto size-8 text-primary" />
        <h1 className={PAGE_TITLE}>You already have access</h1>
        <p className="text-sm text-muted-foreground">
          {ticket.email} has an account. Sign in again and you&rsquo;re in.
        </p>
        <Button className="w-full" onClick={() => (window.location.href = "/login")}>
          Sign in
        </Button>
      </Card>
    );
  }

  if (ticket.pending) {
    return (
      <Card>
        <ClockIcon className="mx-auto size-8 text-muted-foreground" />
        <h1 className={PAGE_TITLE}>Request sent</h1>
        <p className="text-sm text-muted-foreground">
          We&rsquo;ve asked an administrator to give {ticket.email} access.
          You&rsquo;ll get an email as soon as it&rsquo;s approved &mdash;
          there&rsquo;s nothing else to do here.
        </p>
      </Card>
    );
  }

  async function request() {
    setAsking(true);
    setError(null);
    try {
      await api.signup.request();
      await qc.invalidateQueries({ queryKey: ["signup", "me"] });
    } catch (e) {
      // A 409 means they were invited between loading this page and pressing
      // the button — refetching turns the page into the "you already have
      // access" state, which is the true answer rather than an error.
      if (e instanceof ApiError && e.status === 409) {
        await qc.invalidateQueries({ queryKey: ["signup", "me"] });
      } else {
        setError("That didn't go through. Try again.");
      }
    } finally {
      setAsking(false);
    }
  }

  return (
    <Card>
      <LockIcon className="mx-auto size-8 text-muted-foreground" />
      <h1 className={PAGE_TITLE}>Request access</h1>
      <p className="text-sm text-muted-foreground">
        You&rsquo;re signed in as <span className="font-medium text-foreground">{ticket.email}</span>,
        but this address doesn&rsquo;t have access to nSight Studio yet. Ask an
        administrator to approve it.
      </p>
      {error && (
        <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
          {error}
        </p>
      )}
      <Button className="w-full" disabled={asking} onClick={request}>
        {asking ? "Sending…" : "Request access"}
      </Button>
      <p className="text-xs text-muted-foreground">
        You&rsquo;ll get an email when it&rsquo;s approved.
      </p>
    </Card>
  );
}
