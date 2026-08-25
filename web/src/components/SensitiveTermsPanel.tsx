/**
 * The names in this study that must never reach an LLM.
 *
 * nSight generates headlines, themes and summaries by sending the study's own
 * wording to a model. The terms listed here are pseudonymised before that
 * happens — real name out, surrogate in, real name restored in the reply.
 *
 * The list is PROPOSED from the study's own structure, which is where a brand
 * tracker keeps its brands: the members of its batteries and the categories of
 * its questions. That is not a heuristic standing in for entity recognition —
 * on a real Finnish study the shipped NER model found 15% of brand mentions
 * and reading the structure found all nine. But structure cannot tell "Ahne"
 * ("greedy", an image attribute) from "Validia" (a care provider), so a person
 * confirms, and until they do, no report can be created.
 *
 * Being generous is the safe direction: an extra term is masked needlessly, a
 * missing one leaves the building.
 */
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useAcceptSensitiveTerms, useSensitiveTerms } from "@/lib/queries";
import { ApiError } from "@/lib/api";
import { mergeTerms } from "@/lib/sensitiveTerms";
import { formatReportDate } from "@/lib/utils";
import { PANEL_PADDED, PANEL_TITLE } from "@/lib/surfaces";
import { cn } from "@/lib/utils";

export default function SensitiveTermsPanel({
  materialId,
  canEdit,
}: {
  materialId: string | undefined;
  canEdit: boolean;
}) {
  const { data, isLoading } = useSensitiveTerms(materialId);
  const accept = useAcceptSensitiveTerms(materialId);
  const [chosen, setChosen] = useState<Set<string> | null>(null);
  const [adding, setAdding] = useState("");

  // Terms typed in this session. Held separately from `chosen` because the two
  // answer different questions: `chosen` is what will be SAVED, this is what is
  // VISIBLE. Merging them was the bug — a typed term went into `chosen` alone
  // and so never rendered, which looked exactly like the add silently failing.
  const [added, setAdded] = useState<string[]>([]);

  const allTerms = useMemo(
    () => mergeTerms(data?.proposed, data?.accepted, added),
    [data?.proposed, data?.accepted, added]
  );

  // Start from what was accepted before; first time round, nothing is ticked —
  // pre-ticking every proposal would turn "confirm these" into "click OK",
  // which is the review not happening.
  useEffect(() => {
    if (!data || chosen !== null) return;
    setChosen(new Set(data.accepted ?? []));
  }, [data, chosen]);

  if (!materialId) return null;
  if (isLoading || !data || chosen === null) {
    return (
      <section className={PANEL_PADDED}>
        <h2 className={PANEL_TITLE}>Sensitive terms</h2>
        <p className="mt-2 text-sm text-muted-foreground">Reading the study…</p>
      </section>
    );
  }

  // Narrowed once, so the handlers below do not each have to re-prove it.
  const picked: Set<string> = chosen;
  const reviewed = data.accepted !== null;
  const dirty =
    !reviewed ||
    picked.size !== (data.accepted?.length ?? 0) ||
    [...picked].some((t) => !(data.accepted ?? []).includes(t));

  function toggle(term: string) {
    setChosen((prev) => {
      const next = new Set(prev);
      next.has(term) ? next.delete(term) : next.add(term);
      return next;
    });
  }

  function addTerm() {
    const t = adding.trim();
    if (!t) return;
    // Tick it AND show it. A term that is only ticked is invisible, and one
    // that is only shown would be dropped on save.
    const already = allTerms.find((x) => x.toLowerCase() === t.toLowerCase());
    setChosen((prev) => new Set(prev).add(already ?? t));
    if (!already) setAdded((prev) => [...prev, t]);
    setAdding("");
  }

  function save() {
    accept.mutate([...picked], {
      onSuccess: () =>
        toast.success(
          picked.size
            ? `${picked.size} term${picked.size === 1 ? "" : "s"} will be hidden from the AI`
            : "Recorded: this study names no companies"
        ),
      // A 503 means the terms did not reach the store, so nothing was accepted
      // and nothing would be masked. Say that, rather than "save failed".
      onError: (e) =>
        toast.error(
          e instanceof ApiError && e.status === 503
            ? "The terms could not be registered, so they have not been accepted. Please try again."
            : `Could not accept the terms: ${e instanceof Error ? e.message : "unknown error"}`
        ),
    });
  }

  return (
    <section className={PANEL_PADDED}>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className={PANEL_TITLE}>Sensitive terms</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            These names are replaced before anything is sent to the AI, and put
            back in what it writes. Tick every company or brand — including
            competitors.
          </p>
        </div>
        {reviewed && !dirty && (
          <span className="shrink-0 rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
            Accepted
          </span>
        )}
      </div>

      {!reviewed && (
        <p className="mt-3 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
          Reports cannot be created until these are accepted.
        </p>
      )}

      {allTerms.length === 0 ? (
        <p className="mt-3 text-sm text-muted-foreground">
          Nothing in this study's structure looks like a company name. Add any
          you know of, or accept an empty list to confirm there are none.
        </p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-2">
          {allTerms.map((term) => {
            const on = picked.has(term);
            return (
              <li key={term}>
                <button
                  type="button"
                  disabled={!canEdit}
                  onClick={() => toggle(term)}
                  aria-pressed={on}
                  className={cn(
                    "rounded-full border px-3 py-1 text-sm transition-colors",
                    on
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-border bg-surface text-muted-foreground hover:text-foreground",
                    !canEdit && "cursor-default opacity-70"
                  )}
                >
                  {term}
                </button>
              </li>
            );
          })}
        </ul>
      )}

      {canEdit && (
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <input
            value={adding}
            onChange={(e) => setAdding(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTerm())}
            placeholder="Add term"
            className="h-9 min-w-56 flex-1 rounded-md border bg-surface px-3 text-sm"
          />
          <Button type="button" variant="outline" onClick={addTerm} disabled={!adding.trim()}>
            Add
          </Button>
          <Button type="button" onClick={save} disabled={!dirty || accept.isPending}>
            {accept.isPending
              ? "Accepting…"
              : reviewed
                ? "Update"
                : `Accept ${picked.size} term${picked.size === 1 ? "" : "s"}`}
          </Button>
        </div>
      )}

      {reviewed && data.accepted_by && (
        <p className="mt-3 text-xs text-muted-foreground">
          Accepted by {data.accepted_by}
          {data.accepted_at ? ` · ${formatReportDate(data.accepted_at)}` : ""}
        </p>
      )}
    </section>
  );
}
