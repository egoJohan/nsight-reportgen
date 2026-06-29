import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { PlusIcon, FolderIcon, ArrowRightIcon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useCases } from "@/lib/queries";
import NewCaseDialog from "@/components/NewCaseDialog";

export default function CasesPage() {
  const navigate = useNavigate();
  const { data: cases, isLoading, isError } = useCases();
  const [newCaseOpen, setNewCaseOpen] = useState(false);

  const recent = (cases ?? []).slice(-6).reverse();

  return (
    <div className="relative isolate min-h-full">
      {/* Subtle tiled analytics-doodle backdrop (its own stacking context via
          `isolate` so the -z layer isn't hidden behind an opaque ancestor). */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 -z-10 opacity-[0.22]"
        style={{
          backgroundImage: "url(/nsight-background.jpeg)",
          backgroundRepeat: "repeat",
          backgroundSize: "620px auto",
        }}
      />

      <div className="mx-auto w-full max-w-4xl px-6 py-16">
        {/* Welcome hero */}
        <div className="flex flex-col items-center text-center">
          <div className="flex items-center justify-center rounded-2xl bg-primary px-7 py-5 shadow-sm">
            <img src="/nsight-logo.svg" alt="nSight" className="h-12 w-auto" />
          </div>
          <h1 className="mt-7 text-3xl font-semibold tracking-tight">
            Welcome to nSight Studio
          </h1>
          <p className="mt-2 max-w-md text-sm leading-relaxed text-muted-foreground">
            Turn SPSS survey data into polished, on-brand chart reports. Import a
            dataset to create a case, then build reports from its questions.
          </p>
          <Button className="mt-7" size="lg" onClick={() => setNewCaseOpen(true)}>
            <PlusIcon className="size-4" />
            New case
          </Button>
        </div>

        {/* Recent cases */}
        <div className="mt-16">
          <h2 className="mb-3 text-sm font-medium tracking-wide text-muted-foreground uppercase">
            Recent cases
          </h2>

          {isLoading ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-16 w-full rounded-xl" />
              ))}
            </div>
          ) : isError ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/5 px-6 py-8 text-center text-sm text-destructive">
              Failed to load cases. Is the backend running?
            </div>
          ) : recent.length === 0 ? (
            <div className="rounded-xl border border-dashed bg-card/60 py-12 text-center">
              <FolderIcon className="mx-auto mb-3 size-7 text-muted-foreground/50" />
              <p className="text-sm font-medium">No cases yet</p>
              <p className="mt-1 text-sm text-muted-foreground">
                Import an SPSS file to create your first case.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {recent.map((c) => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => navigate(`/cases/${c.id}`)}
                  className="group flex items-center gap-4 rounded-xl border bg-card px-5 py-4 text-left shadow-sm transition-colors hover:border-primary/30 hover:bg-accent/50"
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
      </div>

      <NewCaseDialog open={newCaseOpen} onOpenChange={setNewCaseOpen} />
    </div>
  );
}
