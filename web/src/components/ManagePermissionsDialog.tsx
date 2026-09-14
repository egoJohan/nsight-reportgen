import { useState } from "react";
import { UserIcon, XIcon, GlobeIcon, LockIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  useCustomerAccess, useSetCustomerAccess, useSetPermissionMode,
} from "@/lib/queries";
import type { AccessMode, PermissionMode } from "@/lib/api";
import { EMPTY, ITEM_ROW, ITEM_TITLE } from "@/lib/surfaces";

/** How this customer decides who reaches it.
 *
 *  Two answers, because they are two arrangements and the old dialog could
 *  express only one. "Inherit" is what every customer did before: the Domains
 *  setting applies and the people below are named ON TOP of it. "Manual" takes
 *  nothing from Domains — the list below IS the access list.
 *  (Johan, 2026-09-14) */
const MODE_LABELS: Record<PermissionMode, string> = {
  inherit: "Inherit — the Domains setting applies",
  manual: "Manual — only the people listed here",
};

/** Opened from the customer page's header, by whoever administers this
 *  customer: its OWNER, or an admin for a customer recorded before ownership
 *  existed.
 *
 *  Everything here is customer-scoped on purpose. It used to read `GET /users`
 *  and write `PUT /users/{id}/grants` — both admin-only, and the second one
 *  replaces a person's WHOLE grant list, so handing it to an owner would hand
 *  them every customer in the tenant. `GET`/`PUT /customers/{id}/access` touch
 *  one entry for one person on this one customer, which is what an owner
 *  should be able to do and no more. */
export default function ManagePermissionsDialog({
  open,
  onOpenChange,
  customerId,
  customerName,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  customerId: string;
  customerName: string;
}) {
  // Only while the dialog is open: this discloses a roster, so it is not
  // fetched for every customer page that merely renders the button.
  const { data: access, isLoading, error } = useCustomerAccess(customerId, open);
  const setAccess = useSetCustomerAccess(customerId);
  const setMode = useSetPermissionMode(customerId);
  const [pickedId, setPickedId] = useState("");
  const [pickedMode, setPickedMode] = useState<AccessMode>("view");

  const mode: PermissionMode = access?.permission_mode ?? "inherit";
  const people = access?.people ?? [];
  const candidates = access?.candidates ?? [];

  function write(userId: string, next: AccessMode | null) {
    setAccess.mutate({ userId, mode: next }, {
      onError: (e) => toast.error(e instanceof Error ? e.message : "Could not save"),
    });
  }

  function add() {
    if (!pickedId) return;
    write(pickedId, pickedMode);
    setPickedId("");
    setPickedMode("view");
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Manage permissions</DialogTitle>
          <DialogDescription>
            Who can see {customerName}. Being an admin does not by itself grant
            access — add them below like anyone else.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <div className={EMPTY}>
            <p className="text-sm text-muted-foreground">
              Only this customer's owner can manage its permissions.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">
                Permission management
              </label>
              <Select
                items={MODE_LABELS}
                value={mode}
                disabled={setMode.isPending || isLoading}
                onValueChange={(v) =>
                  setMode.mutate(v as PermissionMode, {
                    onError: (e) =>
                      toast.error(e instanceof Error ? e.message : "Could not save"),
                  })
                }
              >
                <SelectTrigger className="h-9 w-full" aria-label="Permission management">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {(Object.keys(MODE_LABELS) as PermissionMode[]).map((m) => (
                    <SelectItem key={m} value={m}>{MODE_LABELS[m]}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="flex items-start gap-1.5 text-xs text-muted-foreground">
                {mode === "manual" ? (
                  <>
                    <LockIcon className="mt-0.5 size-3.5 shrink-0" />
                    <span>
                      This customer takes nothing from the Domains setting. Only the
                      people listed below can reach it — {candidates.length} other{" "}
                      {candidates.length === 1 ? "person" : "people"} in this hive
                      cannot.
                    </span>
                  </>
                ) : (
                  <>
                    <GlobeIcon className="mt-0.5 size-3.5 shrink-0" />
                    <span>
                      Anyone your Domains setting covers can already reach this
                      customer. The people below are named on top of that — switch to
                      Manual to make this list the only way in.
                    </span>
                  </>
                )}
              </p>
            </div>

            <div className="flex items-center gap-2">
              <select
                aria-label="Add a person"
                className="h-8 min-w-0 flex-1 rounded-lg border border-input bg-surface px-2.5 text-sm"
                value={pickedId}
                onChange={(e) => setPickedId(e.target.value)}
              >
                <option value="">Add a person…</option>
                {candidates.map((c) => (
                  <option key={c.id} value={c.id}>{c.email}</option>
                ))}
              </select>
              <select
                aria-label="Access level for the new person"
                className="h-8 w-24 shrink-0 rounded-lg border border-input bg-surface px-2.5 text-sm"
                value={pickedMode}
                onChange={(e) => setPickedMode(e.target.value as AccessMode)}
              >
                <option value="view">View</option>
                <option value="edit">Edit</option>
              </select>
              <Button variant="outline" size="sm"
                      disabled={!pickedId || setAccess.isPending} onClick={add}>
                Add
              </Button>
            </div>

            {people.length === 0 ? (
              <div className={EMPTY}>
                <p className="text-sm text-muted-foreground">
                  {isLoading ? "Loading…" : "Nobody is named on this customer yet."}
                </p>
              </div>
            ) : (
              <div className="space-y-1.5">
                {people.map((p) => (
                  <div key={p.id} className={ITEM_ROW}>
                    <UserIcon className="size-4 shrink-0 text-muted-foreground" />
                    <span className={`${ITEM_TITLE} flex-1`}>
                      {p.email}
                      {p.name ? <span className="text-muted-foreground"> · {p.name}</span> : null}
                      {p.is_owner ? <span className="text-muted-foreground"> · owner</span> : null}
                    </span>
                    {/* The owner keeps edit on the customer they own — the
                        server refuses to remove or downgrade it (409), so the
                        dialog does not offer what would only fail. */}
                    <select
                      aria-label={`Access level for ${p.email}`}
                      className="h-8 w-24 shrink-0 rounded-lg border border-input bg-surface px-2.5 text-sm disabled:opacity-60"
                      value={p.mode}
                      disabled={setAccess.isPending || p.is_owner}
                      onChange={(e) => write(p.id, e.target.value as AccessMode)}
                    >
                      <option value="view">View</option>
                      <option value="edit">Edit</option>
                    </select>
                    <Button
                      size="icon-sm"
                      variant="ghost"
                      disabled={setAccess.isPending || p.is_owner}
                      title={p.is_owner ? "The owner always keeps access" : "Remove access"}
                      aria-label={`Remove ${p.email}'s access`}
                      onClick={() => write(p.id, null)}
                    >
                      <XIcon className="size-4" />
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
