import { useMemo, useState } from "react";
import { UserIcon, XIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useUsers, useUserActions } from "@/lib/queries";
import type { StudioUser, UserGrantInput } from "@/lib/api";
import { EMPTY, ITEM_ROW, ITEM_TITLE } from "@/lib/surfaces";

type AccessMode = "view" | "edit";

/** One thing this dialog can grant access to. Only "user" exists today —
 *  the groups task adds `kind: "group"` rows, fed from its own list query
 *  and merged into the same `principals` array below. The row markup, the
 *  mode select and the remove button are all keyed off `kind` + `id`, not
 *  off StudioUser, so a group row is a second branch in `principalsFor`
 *  and a second mutation in `writeGrant` — not a new dialog. */
interface AccessPrincipal {
  kind: "user";
  id: string;
  label: string;
  sublabel: string | null;
  mode: AccessMode | null;
}

function principalsFor(users: StudioUser[] | undefined, customerId: string): AccessPrincipal[] {
  return (users ?? []).map((u) => {
    const grant = u.grants.find((g) => g.scope === customerId);
    return {
      kind: "user",
      id: u.id,
      label: u.email,
      sublabel: u.name || null,
      mode: (grant?.mode as AccessMode | undefined) ?? null,
    };
  });
}

/** Admin-only. Opened from the customer page's header: grants and revokes
 *  access to THIS customer, one user at a time. A grant is a scope+mode
 *  pair inside that user's whole-list grants array (PUT /users/{id}/grants
 *  replaces it wholesale), so every write here first reads that user's
 *  current grants and only ever touches the one entry whose scope is this
 *  customer's id — every other customer they can see is carried through
 *  unchanged. */
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
  const { data: users } = useUsers();
  const actions = useUserActions();
  const principals = useMemo(() => principalsFor(users, customerId), [users, customerId]);
  const withAccess = principals.filter((p) => p.mode !== null);
  const withoutAccess = principals.filter((p) => p.mode === null);
  const [pickedId, setPickedId] = useState("");
  const [pickedMode, setPickedMode] = useState<AccessMode>("view");

  /** Rewrites one user's grant list: every scope but this customer's is
   *  carried through untouched; this customer's entry is set to `mode`, or
   *  dropped entirely when `mode` is null (the "remove access" case). */
  function writeGrant(userId: string, mode: AccessMode | null) {
    const user = users?.find((u) => u.id === userId);
    if (!user) return;
    const rest = user.grants
      .filter((g) => g.scope !== customerId)
      .map((g): UserGrantInput => ({ scope: g.scope, mode: g.mode }));
    const next = mode ? [...rest, { scope: customerId, mode }] : rest;
    actions.setGrants.mutate(
      { userId, grants: next },
      { onError: (e) => toast.error(e.message) }
    );
  }

  function add() {
    if (!pickedId) return;
    writeGrant(pickedId, pickedMode);
    setPickedId("");
    setPickedMode("view");
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Manage permissions</DialogTitle>
          <DialogDescription>
            Choose who can see {customerName}. Being an admin does not by
            itself grant access — add them below like anyone else.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <select
              aria-label="Add a person"
              className="h-8 min-w-0 flex-1 rounded-lg border border-input bg-surface px-2.5 text-sm"
              value={pickedId}
              onChange={(e) => setPickedId(e.target.value)}
            >
              <option value="">Add a person…</option>
              {withoutAccess.map((p) => (
                <option key={p.id} value={p.id}>{p.label}</option>
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
            <Button variant="outline" size="sm" disabled={!pickedId} onClick={add}>
              Add
            </Button>
          </div>

          {withAccess.length === 0 ? (
            <div className={EMPTY}>
              <p className="text-sm text-muted-foreground">Nobody has access to this customer yet.</p>
            </div>
          ) : (
            <div className="space-y-1.5">
              {withAccess.map((p) => (
                <div key={p.id} className={ITEM_ROW}>
                  <UserIcon className="size-4 shrink-0 text-muted-foreground" />
                  <span className={`${ITEM_TITLE} flex-1`}>
                    {p.label}
                    {p.sublabel ? <span className="text-muted-foreground"> · {p.sublabel}</span> : null}
                  </span>
                  <select
                    aria-label={`Access level for ${p.label}`}
                    className="h-8 w-24 shrink-0 rounded-lg border border-input bg-surface px-2.5 text-sm"
                    value={p.mode ?? "view"}
                    disabled={actions.setGrants.isPending}
                    onChange={(e) => writeGrant(p.id, e.target.value as AccessMode)}
                  >
                    <option value="view">View</option>
                    <option value="edit">Edit</option>
                  </select>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    disabled={actions.setGrants.isPending}
                    title="Remove access"
                    aria-label={`Remove ${p.label}'s access`}
                    onClick={() => writeGrant(p.id, null)}
                  >
                    <XIcon className="size-4" />
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Done</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
