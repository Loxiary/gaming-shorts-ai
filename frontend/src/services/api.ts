import type {
  Health,
  Job,
  JobDetail,
  JobKind,
  JobStatus,
  Project,
  ProjectCreate,
  ProjectDetail,
  ProjectUpdate,
  SystemInfo,
} from "./types";

export type ApiErrorKind = "network" | "http";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly code: string | null;

  constructor(kind: ApiErrorKind, message: string, status: number | null, code: string | null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.code = code;
  }
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return "Erreur inconnue";
}

export const BACKEND_UNREACHABLE =
  "Le backend est injoignable (http://127.0.0.1:8000). Lancez-le avec scripts\\start.ps1 puis réessayez.";

interface ValidationIssue {
  loc?: (string | number)[];
  msg?: string;
}

function describeError(body: unknown): { message: string; code: string | null } | null {
  if (!body || typeof body !== "object") return null;
  const b = body as { error?: { code?: string; message?: string }; detail?: unknown };
  if (b.error?.message) return { message: b.error.message, code: b.error.code ?? null };
  if (Array.isArray(b.detail)) {
    const issues = (b.detail as ValidationIssue[])
      .map((d) => {
        const field = d.loc?.filter((p) => p !== "body").join(".");
        const msg = (d.msg ?? "invalide").replace(/^Value error, /, "");
        return field ? `${field} : ${msg}` : msg;
      })
      .join(" ; ");
    return { message: `Données invalides — ${issues}`, code: "validation_error" };
  }
  if (typeof b.detail === "string") return { message: b.detail, code: null };
  return null;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError("network", BACKEND_UNREACHABLE, null, null);
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    const described = describeError(parsed);
    if (!described && response.status >= 500) {
      // Réponse non-JSON (ex. proxy Vite sans backend) : backend arrêté.
      throw new ApiError("network", BACKEND_UNREACHABLE, response.status, null);
    }
    throw new ApiError(
      "http",
      described?.message ?? `Erreur HTTP ${response.status}`,
      response.status,
      described?.code ?? null,
    );
  }
  return parsed as T;
}

export const api = {
  health: () => request<Health>("GET", "/api/health"),
  system: () => request<SystemInfo>("GET", "/api/system"),

  listProjects: () => request<Project[]>("GET", "/api/projects"),
  getProject: (id: string) =>
    request<ProjectDetail>("GET", `/api/projects/${encodeURIComponent(id)}`),
  createProject: (data: ProjectCreate) => request<Project>("POST", "/api/projects", data),
  updateProject: (id: string, data: ProjectUpdate) =>
    request<Project>("PATCH", `/api/projects/${encodeURIComponent(id)}`, data),
  deleteProject: (id: string) =>
    request<void>("DELETE", `/api/projects/${encodeURIComponent(id)}?confirm=true`),

  listJobKinds: () => request<JobKind[]>("GET", "/api/job-kinds"),
  listJobs: (params: { status?: JobStatus; projectId?: string } = {}) => {
    const q = new URLSearchParams();
    if (params.status) q.set("status", params.status);
    if (params.projectId) q.set("project_id", params.projectId);
    const qs = q.toString();
    return request<Job[]>("GET", `/api/jobs${qs ? `?${qs}` : ""}`);
  },
  getJob: (id: string) => request<JobDetail>("GET", `/api/jobs/${encodeURIComponent(id)}`),
  createJob: (projectId: string, kind: string) =>
    request<JobDetail>("POST", "/api/jobs", { project_id: projectId, kind }),
  cancelJob: (id: string) =>
    request<JobDetail>("POST", `/api/jobs/${encodeURIComponent(id)}/cancel`),
  retryJob: (id: string) => request<JobDetail>("POST", `/api/jobs/${encodeURIComponent(id)}/retry`),
};
