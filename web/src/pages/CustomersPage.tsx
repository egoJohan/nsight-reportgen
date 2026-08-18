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
import { ROW, EMPTY, ERROR } from "@/lib/surfaces";

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
      toast.error("Asiakkaan luonti epäonnistui");
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Asiakkaat</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Jokainen tutkimus kuuluu yhteen asiakkaaseen.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <PlusIcon className="mr-2 size-4" />
          Uusi asiakas
        </Button>
      </div>

      <div className="mt-8 space-y-2">
        {isLoading && [0, 1, 2].map((i) => <Skeleton key={i} className="h-16 w-full" />)}

        {isError && (
          <p className={ERROR}>
            Asiakaslistan haku epäonnistui.
          </p>
        )}

        {customers?.length === 0 && (
          <div className={EMPTY}>
            <Building2Icon className="mx-auto size-8 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">
              Ei vielä asiakkaita. Luo ensimmäinen aloittaaksesi.
            </p>
            <Button className="mt-4" onClick={() => setOpen(true)}>
              <PlusIcon className="mr-2 size-4" />
              Uusi asiakas
            </Button>
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
            <DialogTitle>Uusi asiakas</DialogTitle>
            <DialogDescription>
              Asiakkaan nimi annetaan luotaessa; sen voi muuttaa myöhemmin.
            </DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={name}
            placeholder="Asiakkaan nimi"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Peruuta
            </Button>
            <Button onClick={submit} disabled={!name.trim() || createCustomer.isPending}>
              Luo
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
