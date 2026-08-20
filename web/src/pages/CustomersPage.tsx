import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PlusIcon, Building2Icon, ArrowRightIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useCustomers, useCreateCustomer } from "@/lib/queries";
import { EMPTY, ERROR, PAGE, PAGE_HEADER, PAGE_SUB, PAGE_TITLE, ROW } from "@/lib/surfaces";

/** Asiakas list — the navigation root. A case belongs to exactly one customer,
 *  so this sits above the case list rather than beside it. */
export default function CustomersPage() {
  const navigate = useNavigate();
  const { data: customers, isLoading, isError } = useCustomers();
  const createCustomer = useCreateCustomer();
  const [searchParams, setSearchParams] = useSearchParams();
  const [name, setName] = useState("");

  // The sidebar links to /?new=customer rather than reaching into this page's
  // state, so the action works from anywhere in the app.
  const open = searchParams.get("new") === "customer";
  function setOpen(next: boolean) {
    setSearchParams(
      (prev) => {
        const p = new URLSearchParams(prev);
        if (next) p.set("new", "customer");
        else p.delete("new");
        return p;
      },
      { replace: true }
    );
  }

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      const created = await createCustomer.mutateAsync(trimmed);
      setOpen(false);
      setName("");
      navigate(`/customers/${created.id}`);
    } catch {
      toast.error("Could not create the customer");
    }
  }

  return (
    <div className={PAGE}>
      <div className={PAGE_HEADER}>
        <div className="min-w-0">
          <h1 className={PAGE_TITLE}>Customers</h1>
          <p className={PAGE_SUB}>Every study belongs to one customer.</p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <PlusIcon className="mr-2 size-4" />New customer</Button>
      </div>

      <div className="space-y-2">
        {isLoading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}

        {isError && (
          <p className={ERROR}>Could not load the customers.</p>
        )}

        {customers?.length === 0 && (
          <div className={EMPTY}>
            <Building2Icon className="mx-auto size-8 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">No customers yet. Create the first one to get started.</p>
            <Button className="mt-4" onClick={() => setOpen(true)}>
              <PlusIcon className="mr-2 size-4" />New customer</Button>
          </div>
        )}

        {customers?.map((c) => (
          <button
            key={c.id}
            onClick={() => navigate(`/customers/${c.id}`)}
            className={ROW}
          >
            <span className="flex items-center gap-3">
              <Building2Icon className="size-5 text-muted-foreground" />
              <span className="font-medium">{c.name}</span>
            </span>
            <ArrowRightIcon className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          </button>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New customer</DialogTitle>
            <DialogDescription>The name is given at creation and can be changed later.</DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={name}
            placeholder="Customer name"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button onClick={submit} disabled={!name.trim() || createCustomer.isPending}>Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
