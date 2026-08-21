import { useCallback } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";
import type { WorkspaceCaseState, WorkspaceReport } from "./api";

// Per-case workspace, persisted through the API (spec §8) -- moved out of
// localStorage so attaching a different hive brings a user's UI state with
// it. One query key for the WHOLE per-user blob (GET /settings/workspace
// returns every case at once): a case page and the report list both read
// it, and fetching per-case would mean a request per case in the sidebar.

export type { WorkspaceCaseState, WorkspaceReport };

const EMPTY: WorkspaceCaseState = { materialId: null, reports: [] };
const KEY = ["settings", "workspace"] as const;

// Pre-§8 storage: `nsight.ws.<caseId>` in localStorage, unscoped by user (a
// shared machine simply overwrote whoever used it last). On the first load
// after this shipped, any such keys are a colleague's working state that
// would otherwise vanish silently -- worse than a visible reset -- so they
// are folded into the signed-in user's server-side workspace once, then
// removed from localStorage. A case already present server-side wins (it
// means this browser already migrated, or the case was touched from
// elsewhere since); only genuinely new-to-the-server cases are pushed up.
const LEGACY_PREFIX = "nsight.ws.";

function readLegacyState(raw: string | null): WorkspaceCaseState | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<WorkspaceCaseState>;
    return {
      materialId: parsed.materialId ?? null,
      reports: Array.isArray(parsed.reports) ? parsed.reports : [],
    };
  } catch {
    return null;
  }
}

/** Sweep every legacy key out of localStorage unconditionally. Used both
 *  after a key has been migrated (or found not worth migrating) and as a
 *  sign-out safety net: two people sharing a machine must not let the next
 *  signed-in user inherit whatever was left over from before this shipped. */
export function clearLegacyWorkspaceStorage() {
  for (const k of Object.keys(localStorage)) {
    if (k.startsWith(LEGACY_PREFIX)) localStorage.removeItem(k);
  }
}

/** Runs at most once per tab load (react-query dedupes concurrent callers of
 *  the same queryFn, and once the keys are gone there is nothing left to
 *  find). Returns `existing` merged with whatever got migrated, so the very
 *  first paint already reflects it instead of waiting on a second fetch. */
async function migrateLegacyWorkspace(
  existing: Record<string, WorkspaceCaseState>
): Promise<Record<string, WorkspaceCaseState>> {
  const legacyKeys = Object.keys(localStorage).filter((k) => k.startsWith(LEGACY_PREFIX));
  if (legacyKeys.length === 0) return existing;

  let merged = existing;
  await Promise.all(
    legacyKeys.map(async (storageKey) => {
      const caseId = storageKey.slice(LEGACY_PREFIX.length);
      try {
        if (!(caseId in existing)) {
          const state = readLegacyState(localStorage.getItem(storageKey));
          if (state) {
            await api.settings.setCaseWorkspace(caseId, state);
            merged = { ...merged, [caseId]: state };
          }
        }
        localStorage.removeItem(storageKey);
      } catch {
        // Leave this one key for a retry on next load -- the write may have
        // failed only because the network hiccuped, not because the data is
        // bad.
      }
    })
  );
  return merged;
}

function caseState(
  all: Record<string, WorkspaceCaseState> | undefined,
  caseId: string
): WorkspaceCaseState {
  const found = all?.[caseId];
  return found
    ? { materialId: found.materialId ?? null, reports: found.reports ?? [] }
    : { ...EMPTY };
}

export function useWorkspace(caseId: string) {
  const qc = useQueryClient();
  const query = useQuery({
    queryKey: KEY,
    queryFn: async () => migrateLegacyWorkspace(await api.settings.workspace()),
  });
  const workspace = caseState(query.data, caseId);

  const write = useMutation({
    mutationFn: (state: WorkspaceCaseState) => api.settings.setCaseWorkspace(caseId, state),
    // Applied before the round trip returns -- a case page reads this
    // synchronously (materialId drives which questions/preview show), and
    // waiting for the network would flash the OLD material back in.
    onMutate: async (state) => {
      await qc.cancelQueries({ queryKey: KEY });
      const previous = qc.getQueryData<Record<string, WorkspaceCaseState>>(KEY);
      qc.setQueryData<Record<string, WorkspaceCaseState>>(KEY, (old) => ({
        ...old,
        [caseId]: state,
      }));
      return { previous };
    },
    onError: (_e, _state, ctx) => {
      if (ctx?.previous) qc.setQueryData(KEY, ctx.previous);
    },
  });

  const setMaterial = useCallback(
    (materialId: string | null) => write.mutate({ ...workspace, materialId }),
    [write, workspace]
  );
  const addReport = useCallback(
    (report: WorkspaceReport) => {
      if (workspace.reports.some((r) => r.id === report.id)) return;
      write.mutate({ ...workspace, reports: [...workspace.reports, report] });
    },
    [write, workspace]
  );
  const removeReport = useCallback(
    (id: string) =>
      write.mutate({ ...workspace, reports: workspace.reports.filter((r) => r.id !== id) }),
    [write, workspace]
  );
  const renameReport = useCallback(
    (id: string, name: string) =>
      write.mutate({
        ...workspace,
        reports: workspace.reports.map((r) => (r.id === id ? { ...r, name } : r)),
      }),
    [write, workspace]
  );

  return { workspace, setMaterial, addReport, removeReport, renameReport };
}

/** Drop this user's state for one case -- e.g. when a case is deleted. */
export function useClearWorkspace() {
  const qc = useQueryClient();
  return useCallback(
    (caseId: string) => {
      qc.setQueryData<Record<string, WorkspaceCaseState>>(KEY, (old) => {
        if (!old) return old;
        const { [caseId]: _drop, ...rest } = old;
        return rest;
      });
      // The empty write both persists the clear and matches what
      // set_case_workspace already does for "no state" -- there is no
      // DELETE route to add for a case this rarely goes empty.
      return api.settings.setCaseWorkspace(caseId, { ...EMPTY });
    },
    [qc]
  );
}
