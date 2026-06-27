import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

// ---- Query keys ----
export const qk = {
  cases: () => ["cases"] as const,
  questions: (materialId: string) => ["questions", materialId] as const,
  variables: (materialId: string) => ["variables", materialId] as const,
};

// ---- Hooks ----

export function useCases() {
  return useQuery({ queryKey: qk.cases(), queryFn: api.cases.list });
}

export function useCreateCase() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.cases.create(name),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.cases() }),
  });
}

export function useQuestions(materialId: string | null) {
  return useQuery({
    queryKey: qk.questions(materialId ?? ""),
    queryFn: () => api.materials.questions(materialId!),
    enabled: !!materialId,
    select: (d) => d.questions,
  });
}

export function useVariables(materialId: string | null) {
  return useQuery({
    queryKey: qk.variables(materialId ?? ""),
    queryFn: () => api.materials.variables(materialId!),
    enabled: !!materialId,
    select: (d) => d.variables,
  });
}

export function useUploadMaterial(caseId: string) {
  return useMutation({
    mutationFn: (file: File) => api.materials.upload(caseId, file),
  });
}
