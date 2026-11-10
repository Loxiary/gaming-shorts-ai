// Types alignés sur les schémas Pydantic du backend (backend/app/schemas/api.py).

export type JobStatus = "queued" | "running" | "completed" | "failed" | "cancelled";
export type StepStatus = "pending" | "running" | "completed" | "failed" | "cancelled";

export interface JobCounts {
  total: number;
  queued: number;
  running: number;
  completed: number;
  failed: number;
  cancelled: number;
}

export interface Project {
  id: string;
  name: string;
  game: string | null;
  description: string | null;
  is_test: boolean;
  created_at: string;
  updated_at: string;
  job_counts: JobCounts;
}

export interface Job {
  id: string;
  project_id: string;
  project_name: string;
  kind: string;
  kind_label: string;
  is_demo: boolean;
  status: JobStatus;
  progress: number;
  current_step: string | null;
  current_step_label: string | null;
  current_step_detail: string | null;
  error_message: string | null;
  cancel_requested: boolean;
  attempts: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  updated_at: string;
}

export interface JobStep {
  position: number;
  name: string;
  label: string;
  status: StepStatus;
  progress: number;
  detail: string | null;
  output: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobDetail extends Job {
  steps: JobStep[];
}

export type RightsStatus = "unknown" | "owned" | "authorized" | "licensed";

export interface Source {
  id: string;
  source_type: string;
  url: string;
  external_id: string;
  rights_status: RightsStatus;
  rights_note: string | null;
  title: string | null;
  uploader: string | null;
  channel_url: string | null;
  upload_date: string | null;
  platform_license: string | null;
  duration_seconds: number | null;
  media_available: boolean;
  media_size_bytes: number | null;
  audio_available: boolean;
  width: number | null;
  height: number | null;
  fps: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  has_audio: boolean | null;
  created_at: string;
}

export interface TranscriptSummary {
  id: string;
  kind: string;
  engine: string;
  model: string;
  device: string;
  compute_type: string;
  language: string | null;
  language_probability: number | null;
  audio_duration_seconds: number | null;
  processing_seconds: number | null;
  segment_count: number;
  created_at: string;
}

export interface Word {
  start: number;
  end: number;
  word: string;
  probability: number | null;
}

export interface TranscriptSegment {
  position: number;
  start_seconds: number;
  end_seconds: number;
  text: string;
  avg_logprob: number | null;
  no_speech_prob: number | null;
  words: Word[];
}

export interface Transcript extends TranscriptSummary {
  segments: TranscriptSegment[];
}

export interface ProjectDetail extends Project {
  jobs: Job[];
  source: Source | null;
  transcript: TranscriptSummary | null;
  files_size_bytes: number;
}

export interface ImportRequest {
  urls: string[];
  rights_status: RightsStatus;
  rights_note?: string | null;
  game?: string | null;
}

export interface ImportResult {
  url: string;
  status: "created" | "duplicate" | "rejected";
  project_id: string | null;
  job_id: string | null;
  message: string | null;
}

export interface ProjectCreate {
  name: string;
  game?: string | null;
  description?: string | null;
  is_test?: boolean;
}

export type ProjectUpdate = Partial<Pick<ProjectCreate, "name" | "game" | "description">>;

export interface JobKind {
  kind: string;
  label: string;
  description: string;
  is_demo: boolean;
  steps: string[];
}

export interface Health {
  status: "ok" | "degraded";
  app: string;
  version: string;
  phase: string;
  database: "ok" | "migration_required";
  database_detail: string | null;
  worker: { alive: boolean; last_seen_at: string | null; worker_id: string | null };
}

export interface SystemInfo {
  app: string;
  version: string;
  phase: string;
  api_host: string;
  api_port: number;
  data_dir: string;
  database_path: string;
  database_size_bytes: number;
  disk_total_bytes: number;
  disk_free_bytes: number;
  data_dirs: { name: string; path: string; exists: boolean; size_bytes: number }[];
  tools: { name: string; found: boolean; path: string | null }[];
  features: { name: string; available: boolean; note: string }[];
  demo_step_seconds: number;
  worker_stale_seconds: number;
  gpu: {
    name: string;
    memory_total_mib: number;
    memory_used_mib: number;
    memory_free_mib: number;
    driver_version: string;
  } | null;
  asr: {
    engine: string;
    model: string;
    model_dir: string;
    model_present: boolean;
    device: string;
    compute_type: string;
    language: string;
    vad: boolean;
  } | null;
  max_download_height: number;
  max_source_minutes: number;
}
