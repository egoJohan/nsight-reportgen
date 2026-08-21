import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { PlusIcon, Building2Icon, ArrowRightIcon, LockIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useCustomers, useCustomerNames, useCreateCustomer } from "@/lib/queries";
import type { Customer } from "@/lib/api";
import { EMPTY, ERROR, PAGE, PAGE_HEADER, PAGE_TITLE, ROW } from "@/lib/surfaces";

/** "3 studies · Owned by Alice" under a customer's name — quiet, secondary
 *  information, the same idea as the studies list's per-study line
 *  (CustomerCasesPage.tsx).
 *
 *  The study count is ALWAYS shown, "0 studies" included: on this page the
 *  number is the fact you are scanning for, and a customer with none should
 *  say so rather than leave you wondering whether it failed to load. Report
 *  counts belong to the studies list, where a report is one row away — here
 *  they were a second number competing with the one that matters.
 *
 *  One owner, the creator; a customer from before ownership was recorded has
 *  none and simply omits the clause. */
function customerSubtitle(c: Customer): string {
  const parts = [`${c.case_count} ${c.case_count === 1 ? "study" : "studies"}`];
  if (c.owner) parts.push(`Owned by ${c.owner.name}`);
  return parts.join(" · ");
}

/** Asiakas list — the navigation root. A case belongs to exactly one customer,
 *  so this sits above the case list rather than beside it. */
export default function CustomersPage() {
  const navigate = useNavigate();
  const { data: customers, isLoading, isError } = useCustomers();
  const { data: allNames } = useCustomerNames();

  // The same one-list rule the sidebar follows: customers you cannot open are
  // listed here too, in their alphabetical place, so this page and the menu
  // agree about what exists. Without them the request flow is unreachable from
  // this page — you can only ask about a customer you can already see.
  const merged = [
    // The full row, stats and owners included, rides along for every
    // customer this caller can actually open.
    ...(customers ?? []).map((c) => ({ id: c.id, name: c.name, accessible: true, customer: c })),
    ...(allNames ?? [])
      .filter((n) => !(customers ?? []).some((c) => c.id === n.id))
      .map((n) => ({ id: n.id, name: n.name, accessible: false, customer: null as Customer | null })),
  ].sort((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: "base" }));
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
        </div>
        <Button variant="outline" onClick={() => setOpen(true)}>
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
            <Button variant="outline" className="mt-4" onClick={() => setOpen(true)}>
              <PlusIcon className="mr-2 size-4" />New customer</Button>
          </div>
        )}

        {merged.map((c) => {
          // Stats only exist for a row this caller can open (see `merged`
          // above). A locked one gets a line too, saying what to do about
          // it — the lock icon alone shows the door is shut without saying
          // it can be opened.
          const subtitle = c.customer
            ? customerSubtitle(c.customer)
            : "Open to request access";
          return (
            <button
              key={c.id}
              onClick={() => navigate(`/customers/${c.id}`)}
              className={ROW}
            >
              <span className="flex min-w-0 items-center gap-3">
                {c.accessible ? (
                  <Building2Icon className="size-5 shrink-0 text-muted-foreground" />
                ) : (
                  <LockIcon className="size-4 shrink-0 text-muted-foreground opacity-70" />
                )}
                <span className="min-w-0 text-left">
                  <span
                    className={
                      "block truncate " +
                      (c.accessible ? "font-medium" : "font-medium text-muted-foreground")
                    }
                  >
                    {c.name}
                  </span>
                  {subtitle && (
                    <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                      {subtitle}
                    </span>
                  )}
                </span>
              </span>
              <ArrowRightIcon className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
            </button>
          );
        })}
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
