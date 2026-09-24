import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2Icon } from "lucide-react";
import { toast } from "sonner";
import { api, type CustomerCase } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/** Deleting a customer removes every study in it permanently — nothing is
 *  kept read-only ("That will just remove all studies permanently" — Johan,
 *  2026-09-24). The dialog names every study and asks for the customer's name
 *  typed back: one click here takes more than any other button in nSight. */
export default function DeleteCustomerDialog({
  open,
  onOpenChange,
  customerId,
  customerName,
  studies,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customerId: string;
  customerName: string;
  /** Undefined while loading: the delete waits until it can say what goes. */
  studies: CustomerCase[] | undefined;
}) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [typed, setTyped] = useState("");
  const [deleting, setDeleting] = useState(false);
  const n = studies?.length ?? 0;
  const studiesWord = n === 1 ? "study" : "studies";
  const confirmed = typed.trim() === customerName.trim() && !!studies;

  async function remove() {
    setDeleting(true);
    try {
      await api.customers.remove(customerId);
      onOpenChange(false);
      toast.success(`Customer “${customerName}” deleted`);
      navigate("/");
      // Every list may have named it or one of its studies.
      qc.invalidateQueries();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete the customer");
    } finally {
      setDeleting(false);
    }
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        if (!v) setTyped("");
        onOpenChange(v);
      }}
    >
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete customer “{customerName}” permanently?</DialogTitle>
          <DialogDescription>
            {n === 0
              ? "The customer has no studies. It is deleted together with its templates."
              : `This permanently deletes the customer and ALL ${n} ${studiesWord} in it.`}
          </DialogDescription>
        </DialogHeader>
        {n > 0 && (
          <div className="space-y-2 text-sm text-muted-foreground">
            <p>
              Nothing is kept read-only: every study's data, reports and generated
              decks (PDF and PPTX) are deleted, as are the customer's templates and
              the permissions given to it.
            </p>
            <ul className="max-h-48 list-disc overflow-y-auto pl-5 font-medium text-foreground">
              {studies!.map((k) => (
                <li key={k.id}>
                  {k.name}
                  {k.dataset_deleted && (
                    <span className="font-normal text-muted-foreground"> (read-only — its decks go too)</span>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        <p className="text-sm font-medium text-destructive">This cannot be undone.</p>
        <label className="space-y-1.5 text-sm">
          <span>
            Type <span className="font-semibold">{customerName}</span> to confirm
          </span>
          <Input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && confirmed && !deleting) remove();
            }}
            autoComplete="off"
          />
        </label>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button variant="destructive" onClick={remove} disabled={!confirmed || deleting}>
            {deleting && <Loader2Icon className="size-4 animate-spin" />}
            {n === 0 ? "Delete customer" : `Delete customer and ${n} ${studiesWord}`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
