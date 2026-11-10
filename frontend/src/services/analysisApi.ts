import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "./api";
import type {
  Analysis,
  AnalysisEngine,
  AnalysisEstimate,
  ApiSettings,
  CostSummary,
  Criterion,
  Profile,
  ProfileInput,
} from "./analysisTypes";
import { POLL_MS } from "./queries";

const enc = encodeURIComponent;

export const analysisApi = {
  listCriteria: () => request<Criterion[]>("GET", "/api/criteria"),
  listProfiles: () => request<Profile[]>("GET", "/api/profiles"),
  createProfile: (data: ProfileInput) => request<Profile>("POST", "/api/profiles", data),
  updateProfile: (id: string, data: ProfileInput) =>
    request<Profile>("PUT", `/api/profiles/${enc(id)}`, data),
  duplicateProfile: (id: string) => request<Profile>("POST", `/api/profiles/${enc(id)}/duplicate`),
  deleteProfile: (id: string) => request<void>("DELETE", `/api/profiles/${enc(id)}`),
  estimate: (projectId: string, profileId?: string) =>
    request<AnalysisEstimate>(
      "GET",
      `/api/projects/${enc(projectId)}/analysis-estimate${profileId ? `?profile_id=${enc(profileId)}` : ""}`,
    ),
  createAnalysis: (projectId: string, profileId: string | null, engine: AnalysisEngine) =>
    request<Analysis>("POST", `/api/projects/${enc(projectId)}/analyses`, {
      profile_id: profileId,
      engine,
    }),
  listAnalyses: (projectId: string) =>
    request<Analysis[]>("GET", `/api/projects/${enc(projectId)}/analyses`),
  getAnalysis: (id: string) => request<Analysis>("GET", `/api/analyses/${enc(id)}`),
  reselect: (id: string, threshold: number) =>
    request<Analysis>("POST", `/api/analyses/${enc(id)}/reselect`, { threshold }),
  apiSettings: () => request<ApiSettings>("GET", "/api/settings/api"),
  updateApiSettings: (data: { api_enabled?: boolean; monthly_cap_usd?: number }) =>
    request<ApiSettings>("PATCH", "/api/settings/api", data),
  costs: () => request<CostSummary>("GET", "/api/costs"),
};

export const useCriteria = () =>
  useQuery({ queryKey: ["criteria"], queryFn: analysisApi.listCriteria, staleTime: Infinity });

export const useProfiles = () =>
  useQuery({ queryKey: ["profiles"], queryFn: analysisApi.listProfiles });

export function useSaveProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string | null; data: ProfileInput }) =>
      id ? analysisApi.updateProfile(id, data) : analysisApi.createProfile(data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useDuplicateProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => analysisApi.duplicateProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export function useDeleteProfile() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => analysisApi.deleteProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}

export const useAnalysisEstimate = (projectId: string, profileId?: string) =>
  useQuery({
    queryKey: ["analysis-estimate", projectId, profileId ?? ""],
    queryFn: () => analysisApi.estimate(projectId, profileId),
  });

export const useAnalyses = (projectId: string) =>
  useQuery({
    queryKey: ["analyses", projectId],
    queryFn: () => analysisApi.listAnalyses(projectId),
    refetchInterval: POLL_MS,
  });

export const useAnalysis = (id: string | undefined, poll: boolean) =>
  useQuery({
    queryKey: ["analysis", id],
    queryFn: () => analysisApi.getAnalysis(id as string),
    enabled: Boolean(id),
    refetchInterval: poll ? POLL_MS : false,
  });

export function useCreateAnalysis(projectId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ profileId, engine }: { profileId: string | null; engine: AnalysisEngine }) =>
      analysisApi.createAnalysis(projectId, profileId, engine),
    onSuccess: () =>
      Promise.all([
        qc.invalidateQueries({ queryKey: ["analyses", projectId] }),
        qc.invalidateQueries({ queryKey: ["projects"] }),
        qc.invalidateQueries({ queryKey: ["jobs"] }),
      ]),
  });
}

export function useReselect(analysisId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (threshold: number) => analysisApi.reselect(analysisId, threshold),
    onSuccess: (data) => {
      qc.setQueryData(["analysis", analysisId], data);
      return qc.invalidateQueries({ queryKey: ["analyses"] });
    },
  });
}

export const useApiSettings = () =>
  useQuery({ queryKey: ["api-settings"], queryFn: analysisApi.apiSettings });

export function useUpdateApiSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: { api_enabled?: boolean; monthly_cap_usd?: number }) =>
      analysisApi.updateApiSettings(data),
    onSuccess: (data) => {
      qc.setQueryData(["api-settings"], data);
      return qc.invalidateQueries({ queryKey: ["analysis-estimate"] });
    },
  });
}

export const useCosts = () => useQuery({ queryKey: ["costs"], queryFn: analysisApi.costs });

export function formatUsd(value: number | null | undefined): string {
  if (value == null) return "—";
  return `${value.toLocaleString("fr-FR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: value > 0 && value < 1 ? 3 : 2,
  })} $`;
}
