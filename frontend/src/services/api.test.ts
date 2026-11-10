import { describe, expect, it } from "vitest";

import { ApiError, BACKEND_UNREACHABLE, api } from "./api";
import { formatBytes, formatDuration } from "./format";
import { mockFetch, mockFetchOffline } from "../test/utils";

describe("client API", () => {
  it("signale un backend injoignable (erreur réseau)", async () => {
    mockFetchOffline();
    const err = await api.listProjects().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect((err as ApiError).kind).toBe("network");
    expect((err as ApiError).message).toBe(BACKEND_UNREACHABLE);
  });

  it("traite une 500 non-JSON (proxy sans backend) comme backend injoignable", async () => {
    mockFetch(() => ({ status: 502, raw: "Bad gateway" }));
    const err = (await api.health().catch((e: unknown) => e)) as ApiError;
    expect(err.kind).toBe("network");
  });

  it("remonte le message d'erreur métier du backend", async () => {
    mockFetch(() => ({
      status: 409,
      body: { error: { code: "conflict", message: "Déjà en file" } },
    }));
    const err = (await api.createJob("p1", "demo").catch((e: unknown) => e)) as ApiError;
    expect(err.kind).toBe("http");
    expect(err.status).toBe(409);
    expect(err.code).toBe("conflict");
    expect(err.message).toBe("Déjà en file");
  });

  it("formate les erreurs de validation FastAPI", async () => {
    mockFetch(() => ({
      status: 422,
      body: { detail: [{ loc: ["body", "name"], msg: "Value error, Le nom est vide" }] },
    }));
    const err = (await api.createProject({ name: " " }).catch((e: unknown) => e)) as ApiError;
    expect(err.message).toBe("Données invalides — name : Le nom est vide");
  });

  it("envoie le corps JSON et la confirmation de suppression", async () => {
    const calls = mockFetch((c) => (c.method === "DELETE" ? { status: 204 } : { body: {} }));
    await api.createProject({ name: "A", is_test: true });
    await api.deleteProject("p 1");
    expect(calls[0]).toMatchObject({
      method: "POST",
      url: "/api/projects",
      body: { name: "A", is_test: true },
    });
    expect(calls[1]).toMatchObject({ method: "DELETE", url: "/api/projects/p%201?confirm=true" });
  });

  it("construit les filtres de la liste des jobs", async () => {
    const calls = mockFetch(() => ({ body: [] }));
    await api.listJobs({ status: "failed", projectId: "p1" });
    expect(calls[0]!.url).toBe("/api/jobs?status=failed&project_id=p1");
  });
});

describe("formatage", () => {
  it("formate les tailles et durées", () => {
    expect(formatBytes(512)).toBe("512 o");
    expect(formatBytes(1536)).toBe("1,5 Ko");
    expect(formatDuration("2026-11-10T10:00:00Z", "2026-11-10T10:01:05Z")).toBe("1 min 05 s");
    expect(formatDuration(null, null)).toBe("—");
  });
});
