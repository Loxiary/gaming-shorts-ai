// Types de la Phase 3, alignés sur backend/app/schemas/analysis.py.

export interface Criterion {
  key: string;
  label: string;
}

export interface Profile {
  id: string;
  name: string;
  description: string | null;
  editorial_focus: string | null;
  threshold: number;
  weights: Record<string, number>;
  output_language: string;
  min_duration: number;
  max_duration: number;
  max_candidates: number;
  use_vision: boolean;
  is_default: boolean;
  subtitle_mode: "source" | "translate" | "off";
  subtitle_style: SubtitleStyle;
  layout: "blur" | "fill";
  zoom_intensity: number;
  hook_enabled: boolean;
  cta_enabled: boolean;
  cta_text: string | null;
  render_encoder: "libx264" | "h264_nvenc";
  // Audio et facecam (Phase 5). Niveaux en dB.
  narration_mode: "auto" | "off";
  narration_voice: string;
  narration_speed: number;
  narration_level_db: number;
  game_level_db: number;
  music_mode: "library" | "off";
  music_level_db: number;
  source_music_mode: "attenuate" | "detect" | "off";
  source_music_reduction_db: number;
  facecam_mode: "crop" | "off";
  created_at: string;
  updated_at: string;
}

export interface SubtitleStyle {
  font: string;
  size: number;
  text_color: string;
  highlight_color: string;
  keyword_color: string;
  uppercase: boolean;
  max_words: number;
}

export type ProfileInput = Omit<Profile, "id" | "created_at" | "updated_at">;

export interface ClipScore {
  criterion: string;
  label: string;
  score: number;
  justification: string | null;
}

export type CandidateStatus = "pending" | "scored" | "signals_only" | "failed" | "refused";

export interface Candidate {
  id: string;
  position: number;
  start_seconds: number;
  end_seconds: number;
  duration_seconds: number;
  peak_seconds: number | null;
  signal_score: number;
  status: CandidateStatus;
  summary: string | null;
  reason: string | null;
  events: { t: number; description: string }[];
  warnings: string[];
  confidence: number | null;
  overall_score: number | null;
  selected: boolean;
  rejection_reason: string | null;
  error_message: string | null;
  transcript_excerpt: string | null;
  scores: ClipScore[];
  frames: { t: number; url: string }[];
  signals: Record<string, unknown>;
}

export interface Analysis {
  id: string;
  project_id: string;
  job_id: string | null;
  profile_id: string | null;
  profile_name: string;
  threshold: number;
  engine: string | null;
  llm_model: string | null;
  use_vision: boolean;
  notes: string[];
  cost_usd: number;
  created_at: string;
  candidate_count: number;
  selected_count: number;
  candidates: Candidate[];
}

export type AnalysisEngine = "auto" | "llm" | "signals";

export interface AnalysisEstimate {
  expected_candidates: number;
  estimated_cost_usd: number;
  key_configured: boolean;
  api_enabled: boolean;
  month_spent_usd: number;
  monthly_cap_usd: number;
  model: string;
}

export interface ApiSettings {
  provider: string;
  model: string;
  effort: string;
  key_configured: boolean;
  api_enabled: boolean;
  monthly_cap_usd: number;
  month_spent_usd: number;
  prices_per_mtok: Record<string, number>;
}

export interface ApiUsage {
  id: string;
  created_at: string;
  provider: string;
  model: string;
  purpose: string;
  project_id: string | null;
  candidate_id: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cache_write_tokens: number;
  images: number;
  cost_usd: number;
  status: string;
  detail: string | null;
}

export interface CostSummary {
  month_spent_usd: number;
  monthly_cap_usd: number;
  total_spent_usd: number;
  calls_this_month: number;
  by_month: { month: string; cost_usd: number; calls: number }[];
  recent: ApiUsage[];
}
