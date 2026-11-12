import type { Render } from "../services/renderApi";
import type { ProjectDetail } from "../services/types";
import { makeProject } from "./utils";

// Rendus et projet factices partagés par les tests des phases 4 et 5.
export function makeRender(overrides: Partial<Render> = {}): Render {
  return {
    id: "r1",
    project_id: "p1",
    candidate_id: "c1",
    job_id: "j1",
    job_status: "completed",
    job_error: null,
    start_seconds: 30,
    end_seconds: 120,
    duration_seconds: 90,
    profile_name: "GTA 6 — Viral",
    plan: {
      hook_text: "Une partie qui démarre fort",
      hook_kind: "original",
      hook_reason: "x",
      cta_text: "Tu aurais fait pareil ?",
      keywords: ["3000"],
      zooms: [{ t: 10, duration: 2, reason: "Explosion" }],
      warnings: [],
    },
    plan_engine: "llm",
    subtitles: [{ start: 0, end: 1, text: "Attention" }],
    subtitle_language: "fr",
    subtitles_are_translation: true,
    video_url: "/api/renders/r1/video",
    output_size_bytes: 25_000_000,
    qc: {
      passed: true,
      checks: [
        {
          key: "duration",
          label: "Durée entre 61 et 180 s",
          ok: true,
          detail: "90 s",
          level: "ok",
        },
        {
          key: "loudness",
          label: "Volume proche de -14 LUFS (±2)",
          ok: false,
          detail: "-18 LUFS",
          level: "warning",
        },
      ],
      measures: {},
    },
    qc_passed: true,
    risk_report: {
      source: {
        title: "Partie",
        creator: "Moi",
        url: "https://y/v",
        platform_license: "non indiquée",
      },
      rights: {
        status: "unknown",
        label: "Inconnu / non vérifié",
        note: null,
        verified_by_app: false,
      },
      audio_music: { status: "non_analysé", detail: "Musique non analysée (Phase 5)." },
      transformation: {
        level: "modérée",
        added: ["recadrage vertical 9:16", "accroche"],
        missing: ["narration originale"],
        detail: "",
      },
      reused_content: { level: "élevé", detail: "Droits non vérifiés." },
      facecam: { status: "non_vérifié", detail: "Facecam non vérifié (Phase 5)." },
      ai_warnings: [],
      qc_warnings: [],
      recommendations: ["Créditez la source."],
      blocking: false,
      disclaimer: "Ce rapport est une aide à la décision.",
    },
    export_warnings: [
      "Droits sur la source non vérifiés.",
      "Musique d'origine non analysée (Phase 5).",
    ],
    ready: true,
    cost_usd: 0.012,
    export_status: "not_exported",
    exported_path: null,
    export_confirmed_at: null,
    acknowledged_warnings: [],
    created_at: "2026-11-11T10:00:00Z",
    ...overrides,
  };
}

export function makeProjectDetail(): ProjectDetail {
  return {
    ...makeProject(),
    jobs: [],
    source: {
      id: "s1",
      source_type: "youtube",
      url: "https://y/v",
      external_id: "abcdefghijk",
      rights_status: "unknown",
      rights_note: null,
      title: "Partie",
      uploader: "Moi",
      channel_url: null,
      upload_date: null,
      platform_license: null,
      duration_seconds: 600,
      media_available: true,
      media_size_bytes: 1,
      audio_available: true,
      width: 1920,
      height: 1080,
      fps: 60,
      video_codec: "h264",
      audio_codec: "aac",
      has_audio: true,
      created_at: "2026-11-10T19:00:00Z",
    },
    transcript: null,
    files_size_bytes: 1,
  };
}
