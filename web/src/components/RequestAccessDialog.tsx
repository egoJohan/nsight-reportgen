import { useEffect, useState } from "react";
import { Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useAccessRequestActions } from "@/lib/queries";
import type { AccessMode } from "@/lib/api";

const MODE_LABEL: Record<AccessMode, string> = {
  view: "View — see studies and reports",
  edit: "Edit — build and change reports",
};

/** Asks for access on a customer, offering only `allowedModes` — the modes
 *  the caller does not already hold. Two callers, two shapes:
 *
 *  - NoAccessCustomer: nothing held, `allowedModes` is `["view", "edit"]`,
 *    and the requester picks one from a select.
 *  - CustomerCasesPage's header button: already a viewer, `allowedModes` is
 *    `["edit"]` alone — there is nothing to pick, so the select is skipped
 *    and the dialog just says what it is about to send. Never offer a mode
 *    already granted (e.g. "view" to someone who already has it).
 *
 *  A "Send request" primary action — the dialog's one filled button,
 *  everything else outline/ghost (see surfaces.ts). */
export function RequestAccessDialog({
  open,
  onOpenChange,
  customerId,
  customerName,
  allowedModes,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  customerId: string;
  customerName: string;
  allowedModes: AccessMode[];
}) {
  const actions = useAccessRequestActions();
  const [mode, setMode] = useState<AccessMode>(allowedModes[0] ?? "view");
  const single = allowedModes.length <= 1;

  // allowedModes can change under an open dialog (switching customers keeps
  // the component mounted in some trees) — keep the selection inside
  // what's actually on offer rather than silently sending a stale mode.
  useEffect(() => {
    if (!allowedModes.includes(mode)) setMode(allowedModes[0] ?? "view");
  }, [allowedModes, mode]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Request access to {customerName}</DialogTitle>
          <DialogDescription>
            {single
              ? `This asks an admin for ${mode} access. They can grant or refuse it.`
              : "An admin will see this and can grant or refuse it."}
          </DialogDescription>
        </DialogHeader>

        {!single && (
          <div className="flex items-center gap-2">
            <select
              aria-label="Access level to request"
              className="h-8 min-w-0 flex-1 rounded-lg border border-input bg-surface px-2.5 text-sm"
              value={mode}
              onChange={(e) => setMode(e.target.value as AccessMode)}
            >
              {allowedModes.map((m) => (
                <option key={m} value={m}>{MODE_LABEL[m]}</option>
              ))}
            </select>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button
            disabled={actions.create.isPending}
            onClick={() =>
              actions.create.mutate(
                { customerId, mode },
                {
                  onSuccess: () => {
                    toast.success("Request sent");
                    onOpenChange(false);
                  },
                  onError: (e) => toast.error(e.message),
                }
              )
            }
          >
            {actions.create.isPending && <Loader2Icon className="size-4 animate-spin" />}
            Send request
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
