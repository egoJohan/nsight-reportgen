import { useState } from "react";
import { useNavigate, useParams, Link } from "react-router-dom";
import { PlusIcon, FolderIcon, ArrowRightIcon, ChevronLeftIcon } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useCustomer, useCustomerCases, useCreateCustomerCase } from "@/lib/queries";

/** One customer's cases. */
export default function CustomerCasesPage() {
  const { customerId } = useParams<{ customerId: string }>();
  const navigate = useNavigate();
  const { data: customer } = useCustomer(customerId);
  const { data: cases, isLoading, isError } = useCustomerCases(customerId);
  const createCase = useCreateCustomerCase(customerId);
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");

  async function submit() {
    const trimmed = name.trim();
    if (!trimmed) return;
    try {
      const created = await createCase.mutateAsync(trimmed);
      setOpen(false);
      setName("");
      navigate(`/cases/${created.id}`);
    } catch {
      toast.error("Casen luonti epäonnistui");
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-12">
      <Link
        to="/"
        className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeftIcon className="mr-1 size-4" />
        Asiakkaat
      </Link>

      <div className="mt-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            {customer?.name ?? "…"}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Casen oletusnimi on aineiston tiedostonimi.
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <PlusIcon className="mr-2 size-4" />
          Uusi case
        </Button>
      </div>

      <div className="mt-8 space-y-2">
        {isLoading && [0, 1].map((i) => <Skeleton key={i} className="h-16 w-full" />)}

        {isError && (
          <p className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm">
            Caselistan haku epäonnistui.
          </p>
        )}

        {cases?.length === 0 && (
          <div className="rounded-lg border border-dashed p-10 text-center">
            <FolderIcon className="mx-auto size-8 text-muted-foreground" />
            <p className="mt-3 text-sm text-muted-foreground">
              Tällä asiakkaalla ei ole vielä caseja.
            </p>
          </div>
        )}

        {cases?.map((k) => (
          <button
            key={k.id}
            onClick={() => navigate(`/cases/${k.id}`)}
            className="group flex w-full items-center justify-between rounded-lg border bg-card p-4 text-left transition-colors hover:bg-accent"
          >
            <span className="flex items-center gap-3">
              <FolderIcon className="size-5 text-muted-foreground" />
              <span className="font-medium">{k.name}</span>
            </span>
            <ArrowRightIcon className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
          </button>
        ))}
      </div>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Uusi case</DialogTitle>
            <DialogDescription>
              Case kuuluu asiakkaaseen {customer?.name}.
            </DialogDescription>
          </DialogHeader>
          <Input
            autoFocus
            value={name}
            placeholder="Casen nimi"
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit()}
          />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Peruuta
            </Button>
            <Button onClick={submit} disabled={!name.trim() || createCase.isPending}>
              Luo
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
