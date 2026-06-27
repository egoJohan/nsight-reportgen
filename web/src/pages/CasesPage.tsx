import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { PlusIcon, FolderIcon, ArrowRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useCases, useCreateCase } from "@/lib/queries";

function EmptyState({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-6 flex size-16 items-center justify-center rounded-2xl bg-muted">
        <FolderIcon className="size-8 text-muted-foreground" />
      </div>
      <h2 className="mb-2 text-xl font-semibold tracking-tight">No cases yet</h2>
      <p className="mb-8 max-w-xs text-sm text-muted-foreground leading-relaxed">
        Create your first case to start uploading survey data and generating
        insights.
      </p>
      <Button onClick={onNew}>
        <PlusIcon className="size-4" />
        New case
      </Button>
    </div>
  );
}

export default function CasesPage() {
  const navigate = useNavigate();
  const { data: cases, isLoading, isError } = useCases();
  const createCase = useCreateCase();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [name, setName] = useState("");

  function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) return;
    createCase.mutate(trimmed, {
      onSuccess: (res) => {
        setDialogOpen(false);
        setName("");
        toast.success(`Case "${trimmed}" created`);
        navigate(`/cases/${res.case_id}`);
      },
      onError: (err) => {
        toast.error(`Failed to create case: ${err.message}`);
      },
    });
  }

  function handleOpen() {
    setName("");
    setDialogOpen(true);
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-10">
      {/* Page header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Cases</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Each case holds one survey dataset and its reports.
          </p>
        </div>
        <Button onClick={handleOpen} size="sm">
          <PlusIcon className="size-4" />
          New case
        </Button>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-6 py-8 text-center text-sm text-destructive">
          Failed to load cases. Is the backend running?
        </div>
      ) : !cases?.length ? (
        <EmptyState onNew={handleOpen} />
      ) : (
        <div className="divide-y divide-border rounded-xl border bg-card shadow-sm overflow-hidden">
          {cases.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => navigate(`/cases/${c.id}`)}
              className="group flex w-full items-center gap-4 px-6 py-4 text-left transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <div className="flex size-9 items-center justify-center rounded-lg bg-muted shrink-0">
                <FolderIcon className="size-4 text-muted-foreground" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium leading-none truncate">{c.name}</p>
                <p className="mt-1 text-xs text-muted-foreground">{c.id}</p>
              </div>
              <ArrowRightIcon className="size-4 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100 shrink-0" />
            </button>
          ))}
        </div>
      )}

      {/* New case dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>New case</DialogTitle>
            <DialogDescription>
              Give this case a memorable name — typically the client or project.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={handleCreate}>
            <div className="py-4">
              <Label htmlFor="case-name" className="sr-only">
                Case name
              </Label>
              <Input
                id="case-name"
                placeholder="e.g. Attendo Suomi Brand 2025"
                value={name}
                onChange={(e) => setName(e.target.value)}
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setDialogOpen(false)}
              >
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!name.trim() || createCase.isPending}
              >
                {createCase.isPending ? "Creating…" : "Create"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
