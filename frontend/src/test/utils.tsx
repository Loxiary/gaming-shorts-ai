import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";

import { AppRoutes } from "../app/App";
import type { Health, Job, Project } from "../services/types";

export interface Call {
  method: string;
  url: string;
  body: unknown;
}

type Handler = (call: Call) => { status?: number; body?: unknown; raw?: string } | undefined;

/** Remplace fetch par un faux serveur. Les routes non gérées répondent 404. */
export function mockFetch(handler: Handler) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const call: Call = {
      method: init?.method ?? "GET",
      url: String(input),
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    const res = handler(call) ?? {
      status: 404,
      body: { error: { code: "not_found", message: "Introuvable" } },
    };
    const status = res.status ?? 200;
    const text = res.raw ?? (res.body === undefined ? "" : JSON.stringify(res.body));
    return new Response(status === 204 ? null : text, { status });
  });
  vi.stubGlobal("fetch", fn);
  return calls;
}

export function mockFetchOffline() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      throw new TypeError("Failed to fetch");
    }),
  );
}

export function renderApp(path: string) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, refetchInterval: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export const health: Health = {
  status: "ok",
  app: "Gaming Shorts AI",
  version: "0.1.0",
  phase: "Phase 1 — fondations",
  database: "ok",
  database_detail: null,
  worker: { alive: true, last_seen_at: "2026-11-10T20:00:00Z", worker_id: "w1" },
};

const counts = { total: 0, queued: 0, running: 0, completed: 0, failed: 0, cancelled: 0 };

export function makeProject(overrides: Partial<Project> = {}): Project {
  return {
    id: "p1",
    name: "Projet test",
    game: "GTA 6",
    description: null,
    is_test: true,
    created_at: "2026-11-10T19:00:00Z",
    updated_at: "2026-11-10T19:00:00Z",
    job_counts: counts,
    ...overrides,
  };
}

export function makeJob(overrides: Partial<Job> = {}): Job {
  return {
    id: "j1",
    project_id: "p1",
    project_name: "Projet test",
    kind: "demo",
    kind_label: "Démonstration",
    is_demo: true,
    status: "queued",
    progress: 0,
    current_step: null,
    current_step_label: null,
    current_step_detail: null,
    error_message: null,
    cancel_requested: false,
    attempts: 0,
    created_at: "2026-11-10T19:00:00Z",
    started_at: null,
    finished_at: null,
    updated_at: "2026-11-10T19:00:00Z",
    ...overrides,
  };
}
