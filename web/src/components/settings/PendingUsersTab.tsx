/**
 * People waiting to be let in.
 *
 * Everyone listed here authenticated with Google or Microsoft and has no
 * account. That is why the address can be trusted enough to act on: it is a
 * provider's assertion, not something typed into a form, so approving is
 * granting access to a person rather than to a claim.
 *
 * Approving creates an INVITATION — the same thing the Users tab's invite
 * button does, with no grants, because that is how invitations work here:
 * the account comes into being and access is granted afterwards on the Users
 * tab. Offering a grant picker only in this one place would have made
 * approving a stranger a different act from inviting a colleague.
 * Refusing removes the row: a permanent list of outsiders who once knocked
 * serves nobody, and keeping it would stop an address ever asking again after
 * a refusal that only meant "not yet".
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { UserPlusIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api";
import { EMPTY, ERROR } from "@/lib/surfaces";
import { formatReportDate } from "@/lib/utils";

export default function PendingUsersTab() {
  const qc = useQueryClient();
  const { data, isLoading, isError } = useQuery({
    queryKey: ["signup-requests"],
    queryFn: api.signup.pending,
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["signup-requests"] });
    // An approval creates a user and an invitation, so both those screens are
    // now out of date.
    void qc.invalidateQueries({ queryKey: ["users"] });
    void qc.invalidateQueries({ queryKey: ["invites"] });
  };

  const approve = useMutation({
    mutationFn: (id: string) => api.signup.approve(id, []),
    onSuccess: (result) => {
      refresh();
      // The asker was told to expect an email. If none went out, the admin is
      // the only one who can close that loop, so say so rather than claiming
      // success and leaving somebody waiting for a message that never comes.
      toast.success(
        result.emailed
          ? `${result.email} has been invited — we've emailed them. Grant them access on the Users tab.`
          : `${result.email} has been invited. No email was sent (SMTP isn't configured) — send them the link yourself.`
      );
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Could not approve"),
  });

  const refuse = useMutation({
    mutationFn: (id: string) => api.signup.refuse(id),
    onSuccess: () => {
      refresh();
      toast.success("Request removed.");
    },
    onError: (e) => toast.error(e instanceof Error ? e.message : "Could not remove"),
  });

  if (isLoading) return <Skeleton className="h-24 w-full" />;
  if (isError) return <p className={ERROR}>Could not load the pending users.</p>;

  if (!data || data.length === 0) {
    return (
      <div className={EMPTY}>
        <UserPlusIcon className="mx-auto size-8 text-muted-foreground" />
        <p className="mt-3 text-sm text-muted-foreground">
          Nobody is waiting for access.
        </p>
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {data.map((r) => (
        <li key={r.id} className="rounded-lg border bg-surface p-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium">{r.email}</p>
              <p className="mt-0.5 text-xs text-muted-foreground">
                Verified by {r.provider === "google" ? "Google" : "Microsoft"}
                {r.requested_at ? ` · asked ${formatReportDate(r.requested_at)}` : ""}
              </p>
            </div>
            <div className="flex shrink-0 gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={approve.isPending}
                onClick={() => approve.mutate(r.id)}
              >
                {approve.isPending ? "Inviting…" : "Approve"}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={refuse.isPending}
                onClick={() => refuse.mutate(r.id)}
              >
                Reject
              </Button>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}
