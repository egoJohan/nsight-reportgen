import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PlusIcon, FolderIcon, ArrowRightIcon, FileTextIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Card } from "@/components/ui/card";
import { useCases } from "@/lib/queries";
import NewCaseDialog from "@/components/NewCaseDialog";

function StatCard({ label, value, icon }: { label: string; value: number | string; icon: React.ReactNode }) {
  return (
    <Card className="flex-row items-center gap-4 p-5">
      <div className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
        {icon}
      </div>
      <div>
        <p className="text-2xl font-semibold tabular-nums leading-none">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{label}</p>
      </div>
    </Card>
  );
}

export default function CasesPage() {
  const navigate = useNavigate();
  const { data: cases, isLoading, isError } = useCases();
  const [newCaseOpen, setNewCaseOpen] = useState(false);

  const recent = (cases ?? []).slice(-6).reverse();

  return (
    <div className="mx-auto w-full max-w-5xl px-6 py-10">
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Import a survey to create a case, then build chart reports from it.
          </p>
        </div>
        <Button onClick={() => setNewCaseOpen(true)}>
          <PlusIcon className="size-4" />
          New case
        </Button>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-20 w-full rounded-xl" />
          ))}
        </div>
      ) : isError ? (
        <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-6 py-8 text-center text-sm text-destructive">
          Failed to load cases. Is the backend running?
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <StatCard label="Cases" value={cases?.length ?? 0} icon={<FolderIcon className="size-5" />} />
            <StatCard
              label="Get started"
              value="Import a SAV"
              icon={<FileTextIcon className="size-5" />}
            />
          </div>

          {/* Recent cases */}
          <div className="mt-10">
            <h2 className="mb-3 text-sm font-medium tracking-wide text-muted-foreground uppercase">
              Recent cases
            </h2>
            {recent.length === 0 ? (
              <div className="flex flex-col items-center justify-center rounded-xl border border-dashed py-16 text-center">
                <div className="mb-4 flex size-12 items-center justify-center rounded-xl bg-muted">
                  <FolderIcon className="size-6 text-muted-foreground" />
                </div>
                <p className="text-sm font-medium">No cases yet</p>
                <p className="mt-1 max-w-xs text-sm text-muted-foreground">
                  Create your first case by importing an SPSS file.
                </p>
                <Button className="mt-5" onClick={() => setNewCaseOpen(true)}>
                  <PlusIcon className="size-4" />
                  New case
                </Button>
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                {recent.map((c) => (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => navigate(`/cases/${c.id}`)}
                    className="group flex items-center gap-4 rounded-xl border bg-card px-5 py-4 text-left transition-colors hover:border-primary/30 hover:bg-accent/40"
                  >
                    <div className="flex size-9 items-center justify-center rounded-lg bg-muted shrink-0">
                      <FolderIcon className="size-4 text-muted-foreground" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium leading-none">{c.name}</p>
                      <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{c.id}</p>
                    </div>
                    <ArrowRightIcon className="size-4 shrink-0 text-muted-foreground opacity-0 transition-opacity group-hover:opacity-100" />
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <NewCaseDialog open={newCaseOpen} onOpenChange={setNewCaseOpen} />
    </div>
  );
}
