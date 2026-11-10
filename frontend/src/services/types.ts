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
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobDetail extends Job {
  steps: JobStep[];
}

export interface ProjectDetail extends Project {
  jobs: Job[];
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
}
