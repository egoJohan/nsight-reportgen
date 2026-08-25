import { useState } from "react";
import { LockIcon } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useCustomerName, useMyAccessRequests } from "@/lib/queries";
import { accessNoticeFor } from "@/lib/accessNotice";
import { RequestAccessDialog } from "@/components/RequestAccessDialog";
import { PAGE_TITLE } from "@/lib/surfaces";

/** What a signed-in user sees instead of a customer's cases when they hold
 *  no grant on it (spec §5 — the customer is a 404 to every other route).
 *  Reads as an explanation, not an error: this person has done nothing
 *  wrong, they just have not been given access yet.
 *
 *  Fed by `useCustomerName` (GET /customers/{id}/name), the one narrow
 *  exception to the 404-for-absence rule — see routes_customers.py's
 *  `customer_name` for exactly what it does and does not reveal. */
export default function NoAccessCustomer({ customerId }: { customerId: string }) {
  const { data: customer } = useCustomerName(customerId);
  const { data: mine } = useMyAccessRequests();
  const [requesting, setRequesting] = useState(false);
  const qc = useQueryClient();

  const existing = mine
    ?.filter((r) => r.customer_id === customerId)
    .sort((a, b) => (a.requested_at < b.requested_at ? 1 : -1))[0];

  const name = customer?.name ?? "This customer";
  const notice = accessNoticeFor(existing?.state);
  // Set once a re-check has come back and this page is STILL on screen — which
  // is itself the answer, because the parent only renders this component while
  // the customer 404s. Without it the button looked broken: it did refetch,
  // nothing had changed, and nothing said so.
  const [recheckedStillDenied, setRecheckedStillDenied] = useState(false);
  const [rechecking, setRechecking] = useState(false);

  async function recheck() {
    setRechecking(true);
    setRecheckedStillDenied(false);
    try {
      await qc.refetchQueries({ queryKey: ["customer", customerId] });
      setRecheckedStillDenied(true);
    } finally {
      setRechecking(false);
    }
  }

  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed bg-surface px-6 py-16 text-center">
      <LockIcon className="size-8 text-muted-foreground" />
      <h1 className={`${PAGE_TITLE} mt-4`}>{name}</h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">{notice.lead}</p>

      {existing?.state === "pending" && (
        <p className="mt-4 text-xs text-muted-foreground">
          Requested {existing.mode} access on{" "}
          {new Date(existing.requested_at).toLocaleDateString()}.
        </p>
      )}
      {notice.note && (
        <p className="mt-4 text-xs text-muted-foreground">{notice.note}</p>
      )}
      {recheckedStillDenied && (
        <p className="mt-4 text-xs text-muted-foreground">
          Checked just now — you still don&rsquo;t have access.
        </p>
      )}

      <div className="mt-6 flex flex-wrap items-center justify-center gap-2">
        {notice.showRecheck && (
          <Button variant="outline" onClick={recheck} disabled={rechecking}>
            {rechecking ? "Checking…" : "Check again"}
          </Button>
        )}
        {notice.showRequest && (
          <Button variant="outline" onClick={() => setRequesting(true)}>
            Request access
          </Button>
        )}
      </div>

      <RequestAccessDialog
        open={requesting}
        onOpenChange={setRequesting}
        customerId={customerId}
        customerName={name}
        allowedModes={["view", "edit"]}
      />
    </div>
  );
}
