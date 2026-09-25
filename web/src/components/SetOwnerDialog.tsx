import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useUsers } from "@/lib/queries";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** An admin gives an ownerless customer its owner. Offered only while it has
 *  none — the owner's account was removed, or it predates ownership — because
 *  "only when the old owner does not exist anymore" (Johan, 2026-09-25); the
 *  server refuses any other case. The new owner also gets edit on it. */
export default function SetOwnerDialog({
  open,
  onOpenChange,
  customerId,
  customerName,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: string;
  customerName: string;
}) {
  const qc = useQueryClient();
  const { data: users } = useUsers();
  const [picked, setPicked] = useState("");
  const [saving, setSaving] = useState(false);

  async function save() {
    setSaving(true);
    try {
      const r = await api.customers.setOwner(customerId, picked);
      toast.success(`${r.owner.name} now owns ${customerName}`);
      qc.invalidateQueries({ queryKey: ["customer", customerId] });
      qc.invalidateQueries({ queryKey: ["customers"] });
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["customers-without-owner"] });
      onOpenChange(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not set the owner");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) setPicked("");
        onOpenChange(v);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Set an owner for “{customerName}”</DialogTitle>
          <DialogDescription>
            This customer has no owner — the owner's account was removed. The
            owner decides who can reach the customer and can delete it. They
            also get edit access to it.
          </DialogDescription>
        </DialogHeader>
        <select
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
          value={picked}
          onChange={(e) => setPicked(e.target.value)}
        >
          <option value="">Choose a person…</option>
          {(users ?? []).map((u) => (
            <option key={u.id} value={u.id}>
              {u.name ? `${u.name} (${u.email})` : u.email}
            </option>
          ))}
        </select>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={save} disabled={!picked || saving}>
            {saving && <Loader2Icon className="size-4 animate-spin" />}
            Set owner
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
