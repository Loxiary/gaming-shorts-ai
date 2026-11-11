import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "./api";
import { POLL_MS } from "./queries";

const enc = encodeURIComponent;

export interface QcCheck {
  key: string;
  label: string;
  ok: boolean;
  detail: string;
  level: "ok" | "warning" | "critical";
}

export interface RiskReport {
  source: { title: string | null; creator: string | null; url: string; platform_license: string };
  rights: { status: string; label: string; note: string | null; verified_by_app: boolean };
  audio_music: { status: string; detail: string };
  transformation: { level: string; added: string[]; missing: string[]; detail: string };
  reused_content: { level: string; detail: string };
  facecam: { status: string; detail: string };
  credits?: Credit[];
  audio_notes?: string[];
  ai_warnings: string[];
  qc_warnings: string[];
  recommendations: string[];
  blocking: boolean;
  disclaimer: string;
}

export interface Credit {
  kind: "voice" | "music";
  text: string;
}

export interface NarrationLine {
  t: number;
  duration: number;
  text: string;
  moved: boolean;
}

export interface AudioReport {
  source_music: {
    mode: string;
    status: "disabled" | "unavailable" | "none" | "detected";
    attenuated: boolean;
    ratio?: number;
    mean?: number;
    reduction_db?: number;
    residual_ratio?: number;
    per_second?: number[];
  };
  narration: {
    mode: string;
    status: string;
    voice?: string;
    reason?: string;
    lines: NarrationLine[];
    dropped?: string[];
  };
  music: {
    mode: string;
    status: string;
    title?: string;
    artist?: string | null;
    license?: string;
    mood?: string | null;
    level_db?: number;
  };
  sfx?: { mode: string; status: string; level_db?: number; events?: { t: number; kind: string }[] };
  levels: Record<string, number>;
  notes: string[];
}

export interface FacecamResult {
  mode?: string;
  status: string;
  presence?: number;
  frames_analyzed?: number;
  crop: number[] | null;
  crop_side?: string;
  loss?: number;
  warning: string | null;
}

export interface EditorialPlan {
  hook_text: string;
  hook_kind: "quote" | "original";
  hook_reason: string;
  cta_text: string;
  keywords: string[];
  zooms: { t: number; duration: number; reason: string }[];
  warnings: string[];
  narration_needed?: boolean;
  narration_reason?: string;
  narration?: { t: number; text: string }[];
  music_mood?: string;
  effects?: { t: number; kind: "flash" | "shake"; duration: number; reason: string }[];
}

export interface Render {
  id: string;
  project_id: string;
  candidate_id: string | null;
  job_id: string | null;
  job_status: string | null;
  job_error: string | null;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  profile_name: string;
  plan: EditorialPlan | null;
  plan_engine: string | null;
  subtitles: { start: number; end: number; text: string; karaoke?: boolean }[];
  subtitle_language: string | null;
  subtitles_are_translation: boolean;
  video_url: string | null;
  output_size_bytes: number | null;
  qc: { passed: boolean; checks: QcCheck[]; measures: Record<string, number | null> } | null;
  qc_passed: boolean | null;
  risk_report: RiskReport | null;
  audio_report?: AudioReport | null;
  facecam?: FacecamResult | null;
  credits?: Credit[];
  preview_audio_url?: string | null;
  files_purged?: boolean;
  export_warnings: string[];
  ready: boolean;
  cost_usd: number;
  export_status: "not_exported" | "exported";
  exported_path: string | null;
  export_confirmed_at: string | null;
  acknowledged_warnings: string[];
  created_at: string;
}

export const renderApi = {
  create: (candidateId: string) =>
    request<Render>("POST", `/api/candidates/${enc(candidateId)}/renders`, {}),
  list: (projectId: string) => request<Render[]>("GET", `/api/projects/${enc(projectId)}/renders`),
  confirmExport: (id: string) =>
    request<Render>("POST", `/api/renders/${enc(id)}/confirm-export`, { acknowledged: true }),
  renderSelection: (analysisId: string) =>
    request<{ created: Render[]; skipped_candidate_ids: string[] }>(
      "POST",
      `/api/analyses/${enc(analysisId)}/renders`,
      {},
    ),
  remove: (id: string) => request<void>("DELETE", `/api/renders/${enc(id)}?confirm=true`),
  exports: () => request<Render[]>("GET", "/api/exports"),
};

export const useRenders = (projectId: string) =>
  useQuery({
    queryKey: ["renders", projectId],
    queryFn: () => renderApi.list(projectId),
    refetchInterval: POLL_MS,
  });

export const useExports = () => useQuery({ queryKey: ["exports"], queryFn: renderApi.exports });

function useInvalidate() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: ["renders"] }),
      qc.invalidateQueries({ queryKey: ["exports"] }),
      qc.invalidateQueries({ queryKey: ["projects"] }),
      qc.invalidateQueries({ queryKey: ["jobs"] }),
    ]);
}

export function useCreateRender() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => renderApi.create(id), onSuccess: invalidate });
}

export function useRenderSelection() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (analysisId: string) => renderApi.renderSelection(analysisId),
    onSuccess: invalidate,
  });
}

export function useConfirmExport() {
  const invalidate = useInvalidate();
  return useMutation({
    mutationFn: (id: string) => renderApi.confirmExport(id),
    onSuccess: invalidate,
  });
}

export function useDeleteRender() {
  const invalidate = useInvalidate();
  return useMutation({ mutationFn: (id: string) => renderApi.remove(id), onSuccess: invalidate });
}
