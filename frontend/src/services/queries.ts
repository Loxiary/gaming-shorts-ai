import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import type { ImportRequest, JobStatus, ProjectCreate, ProjectUpdate, RightsStatus } from "./types";

// Rafraîchissement périodique : suivi de la progression des jobs sans WebSocket (Phase 1).
export const POLL_MS = 2000;

export const keys = {
  health: ["health"] as const,
  system: ["system"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["projects", id] as const,
  jobs: (filter: { status?: JobStatus; projectId?: string }) => ["jobs", filter] as const,
  job: (id: string) => ["job", id] as const,
  jobKinds: ["job-kinds"] as const,
  transcript: (projectId: string) => ["transcript", projectId] as const,
};

export const useHealth = () =>
  useQuery({ queryKey: keys.health, queryFn: api.health, refetchInterval: 3000, retry: false });

export const useSystem = () => useQuery({ queryKey: keys.system, queryFn: api.system });

export const useProjects = () =>
  useQuery({ queryKey: keys.projects, queryFn: api.listProjects, refetchInterval: POLL_MS });

export const useProject = (id: string) =>
  useQuery({
    queryKey: keys.project(id),
    queryFn: () => api.getProject(id),
    refetchInterval: POLL_MS,
  });

export const useJobs = (filter: { status?: JobStatus; projectId?: string } = {}) =>
  useQuery({
    queryKey: keys.jobs(filter),
    queryFn: () => api.listJobs(filter),
    refetchInterval: POLL_MS,
  });

export const useJob = (id: string, enabled = true) =>
  useQuery({
    queryKey: keys.job(id),
    queryFn: () => api.getJob(id),
    refetchInterval: POLL_MS,
    enabled,
  });

export const useJobKinds = () =>
  useQuery({ queryKey: keys.jobKinds, queryFn: api.listJobKinds, staleTime: Infinity });

function useInvalidateAll() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["projects"] }),
      qc.invalidateQueries({ queryKey: ["jobs"] }),
      qc.invalidateQueries({ queryKey: ["job"] }),
    ]);
}

export function useCreateProject() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (data: ProjectCreate) => api.createProject(data),
    onSuccess: invalidate,
  });
}

export function useUpdateProject(id: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (data: ProjectUpdate) => api.updateProject(id, data),
    onSuccess: invalidate,
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: (_data, id) => {
      qc.removeQueries({ queryKey: keys.project(id) });
      return Promise.all([
        qc.invalidateQueries({ queryKey: ["projects"], exact: true }),
        qc.invalidateQueries({ queryKey: ["jobs"] }),
      ]);
    },
  });
}

export const useTranscript = (projectId: string, enabled: boolean, version?: string) =>
  useQuery({
    queryKey: [...keys.transcript(projectId), version ?? ""],
    queryFn: () => api.getTranscript(projectId),
    enabled,
    staleTime: Infinity,
  });

export function useImportSources() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (data: ImportRequest) => api.importSources(data),
    onSuccess: invalidate,
  });
}

export function useUpdateSource(projectId: string) {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: (data: { rights_status?: RightsStatus; rights_note?: string | null }) =>
      api.updateSource(projectId, data),
    onSuccess: invalidate,
  });
}

export function useCreateJob() {
  const invalidate = useInvalidateAll();
  return useMutation({
    mutationFn: ({ projectId, kind }: { projectId: string; kind: string }) =>
      api.createJob(projectId, kind),
    onSuccess: invalidate,
  });
}

export function useCancelJob() {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: (id: string) => api.cancelJob(id), onSuccess: invalidate });
}

export function usePauseJob() {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: (id: string) => api.pauseJob(id), onSuccess: invalidate });
}

export function useResumeJob() {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: (id: string) => api.resumeJob(id), onSuccess: invalidate });
}

export function useRetryJob() {
  const invalidate = useInvalidateAll();
  return useMutation({ mutationFn: (id: string) => api.retryJob(id), onSuccess: invalidate });
}
