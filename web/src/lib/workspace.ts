import { useCallback, useEffect, useState } from "react";

// Per-case workspace, persisted in localStorage (no backend list endpoint).

export interface WorkspaceReport {
  id: string;
  name: string;
  // Material the report's charts were built against. Optional so legacy
  // entries persisted before this field tolerate parsing (left undefined).
  materialId?: string;
}

export interface WorkspaceState {
  materialId: string | null;
  reports: WorkspaceReport[];
}

const EMPTY: WorkspaceState = { materialId: null, reports: [] };

function key(caseId: string): string {
  return `nsight.ws.${caseId}`;
}

export function getWorkspace(caseId: string): WorkspaceState {
  try {
    const raw = localStorage.getItem(key(caseId));
    if (!raw) return { ...EMPTY };
    const parsed = JSON.parse(raw) as Partial<WorkspaceState>;
    return {
      materialId: parsed.materialId ?? null,
      reports: Array.isArray(parsed.reports) ? parsed.reports : [],
    };
  } catch {
    return { ...EMPTY };
  }
}

function write(caseId: string, state: WorkspaceState) {
  try {
    localStorage.setItem(key(caseId), JSON.stringify(state));
  } catch {
    // ignore quota / private-mode failures
  }
  // Notify same-tab listeners (storage event only fires cross-tab).
  window.dispatchEvent(new CustomEvent("nsight-workspace", { detail: caseId }));
}

export function setMaterial(caseId: string, materialId: string | null) {
  const next = { ...getWorkspace(caseId), materialId };
  write(caseId, next);
}

export function clearWorkspace(caseId: string) {
  try {
    localStorage.removeItem(key(caseId));
  } catch {
    // ignore
  }
  window.dispatchEvent(new CustomEvent("nsight-workspace", { detail: caseId }));
}

export function addReport(caseId: string, report: WorkspaceReport) {
  const ws = getWorkspace(caseId);
  if (ws.reports.some((r) => r.id === report.id)) return;
  write(caseId, { ...ws, reports: [...ws.reports, report] });
}

export function removeReport(caseId: string, id: string) {
  const ws = getWorkspace(caseId);
  write(caseId, { ...ws, reports: ws.reports.filter((r) => r.id !== id) });
}

export function renameReport(caseId: string, id: string, name: string) {
  const ws = getWorkspace(caseId);
  write(caseId, {
    ...ws,
    reports: ws.reports.map((r) => (r.id === id ? { ...r, name } : r)),
  });
}

// ---- React hook ----
export function useWorkspace(caseId: string) {
  const [state, setState] = useState<WorkspaceState>(() =>
    getWorkspace(caseId)
  );

  useEffect(() => {
    setState(getWorkspace(caseId));
    const refresh = () => setState(getWorkspace(caseId));
    const onCustom = (e: Event) => {
      if ((e as CustomEvent).detail === caseId) refresh();
    };
    window.addEventListener("nsight-workspace", onCustom);
    window.addEventListener("storage", refresh);
    return () => {
      window.removeEventListener("nsight-workspace", onCustom);
      window.removeEventListener("storage", refresh);
    };
  }, [caseId]);

  return {
    workspace: state,
    setMaterial: useCallback(
      (materialId: string | null) => setMaterial(caseId, materialId),
      [caseId]
    ),
    addReport: useCallback(
      (report: WorkspaceReport) => addReport(caseId, report),
      [caseId]
    ),
    removeReport: useCallback(
      (id: string) => removeReport(caseId, id),
      [caseId]
    ),
    renameReport: useCallback(
      (id: string, name: string) => renameReport(caseId, id, name),
      [caseId]
    ),
  };
}
