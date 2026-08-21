import { useState } from "react";
import { LockIcon } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { useCustomerName, useMyAccessRequests } from "@/lib/queries";
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

  return (
    <div className="flex flex-col items-center rounded-xl border border-dashed bg-surface px-6 py-16 text-center">
      <LockIcon className="size-8 text-muted-foreground" />
      <h1 className={`${PAGE_TITLE} mt-4`}>{name}</h1>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        You don&rsquo;t have access to {name} yet. Request view or edit access
        and an admin will review it.
      </p>

      {existing?.state === "pending" ? (
        <p className="mt-6 text-sm text-muted-foreground">
          Requested {existing.mode} access on{" "}
          {new Date(existing.requested_at).toLocaleDateString()} — waiting on an admin.
        </p>
      ) : existing?.state === "granted" ? (
        <div className="mt-6 space-y-3">
          <p className="text-sm text-primary">Access granted.</p>
          <Button
            variant="outline"
            onClick={() =>
              qc.invalidateQueries({ queryKey: ["customer", customerId] })
            }
          >
            Continue
          </Button>
        </div>
      ) : (
        <>
          {existing?.state === "refused" && (
            <p className="mt-4 text-xs text-muted-foreground">
              A previous request was refused. You can ask again.
            </p>
          )}
          <Button variant="outline" className="mt-6" onClick={() => setRequesting(true)}>
            Request access
          </Button>
        </>
      )}

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
