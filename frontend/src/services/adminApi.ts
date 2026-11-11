// Phase 6 : réglages globaux, stockage, sauvegardes, export/import des profils.
// Aligné sur backend/app/api/routes_admin.py.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import type { Profile } from "./analysisTypes";
import { request } from "./api";

export type SettingValue = string | number | boolean;

export interface RuntimeSetting {
  key: string;
  label: string;
  group: string;
  help: string;
  type: "int" | "float" | "bool" | "choice" | "str";
  choices: string[];
  min: number | null;
  max: number | null;
  value: SettingValue;
  env_value: SettingValue;
  overridden: boolean;
}

export interface ProjectUsage {
  project_id: string;
  name: string;
  source_bytes: number;
  analysis_bytes: number;
  renders_bytes: number;
  total_bytes: number;
  last_activity: string | null;
}

export interface Storage {
  data_dir: string;
  disk_total_bytes: number;
  disk_free_bytes: number;
  min_free_disk_gb: number;
  directories: Record<string, number>;
  database_bytes: number;
  db_backups_bytes: number;
  projects: ProjectUsage[];
  retention: { temp_days: number; render_days: number; source_days: number; auto: boolean };
  categories: Record<string, string>;
}

export interface CleanupResult {
  dry_run: boolean;
  categories: string[];
  files: number;
  bytes: number;
  items: {
    category: string;
    path: string;
    bytes: number;
    reason: string;
    project_id: string | null;
  }[];
  truncated: boolean;
  errors: string[];
}

export interface Backup {
  name: string;
  size_bytes: number;
  created_at: string | null;
  app_version: string | null;
  schema_revision: string | null;
  counts: Record<string, number | null>;
  valid: boolean;
}

const enc = encodeURIComponent;

export const adminApi = {
  runtime: () => request<RuntimeSetting[]>("GET", "/api/settings/runtime"),
  saveRuntime: (values: Record<string, SettingValue | null>) =>
    request<RuntimeSetting[]>("PUT", "/api/settings/runtime", { values }),
  storage: () => request<Storage>("GET", "/api/storage"),
  cleanup: (categories: string[], dryRun: boolean) =>
    request<CleanupResult>("POST", "/api/storage/cleanup", { categories, dry_run: dryRun }),
  backups: () => request<Backup[]>("GET", "/api/backups"),
  createBackup: () => request<Backup>("POST", "/api/backups"),
  deleteBackup: (name: string) => request<void>("DELETE", `/api/backups/${enc(name)}?confirm=true`),
  backupUrl: (name: string) => `/api/backups/${enc(name)}`,
  profilesExportUrl: "/api/profiles-export",
  importProfiles: (doc: unknown) => request<Profile[]>("POST", "/api/profiles-import", doc),
};

export const useRuntimeSettings = () =>
  useQuery({ queryKey: ["runtime-settings"], queryFn: adminApi.runtime });
export const useStorage = () => useQuery({ queryKey: ["storage"], queryFn: adminApi.storage });
export const useBackups = () => useQuery({ queryKey: ["backups"], queryFn: adminApi.backups });

export function useSaveRuntime() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: adminApi.saveRuntime,
    onSuccess: (data) => {
      qc.setQueryData(["runtime-settings"], data);
      return qc.invalidateQueries({ queryKey: ["storage"] });
    },
  });
}

export function useCleanup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ categories, dryRun }: { categories: string[]; dryRun: boolean }) =>
      adminApi.cleanup(categories, dryRun),
    onSuccess: (data) =>
      data.dry_run
        ? undefined
        : Promise.all([
            qc.invalidateQueries({ queryKey: ["storage"] }),
            qc.invalidateQueries({ queryKey: ["projects"] }),
            qc.invalidateQueries({ queryKey: ["renders"] }),
          ]),
  });
}

export function useCreateBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: adminApi.createBackup,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });
}

export function useDeleteBackup() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: adminApi.deleteBackup,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });
}

export function useImportProfiles() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: adminApi.importProfiles,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["profiles"] }),
  });
}
