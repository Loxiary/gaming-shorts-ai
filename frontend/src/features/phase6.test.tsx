import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { RuntimeSetting, Storage } from "../services/adminApi";
import { health, makeJob, mockFetch, renderApp } from "../test/utils";

const runtime: RuntimeSetting[] = [
  {
    key: "frames_per_candidate",
    label: "Images envoyées par extrait",
    group: "IA",
    help: "0 à 20.",
    type: "int",
    choices: [],
    min: 0,
    max: 20,
    value: 8,
    env_value: 8,
    overridden: false,
  },
  {
    key: "retention_temp_days",
    label: "Fichiers intermédiaires (jours)",
    group: "Stockage",
    help: "0 = jamais.",
    type: "int",
    choices: [],
    min: 0,
    max: 3650,
    value: 3,
    env_value: 7,
    overridden: true,
  },
];

const storage: Storage = {
  data_dir: "D:/GamingShortsAI/data",
  disk_total_bytes: 500e9,
  disk_free_bytes: 200e9,
  min_free_disk_gb: 5,
  directories: { sources: 197e6, exports: 0 },
  database_bytes: 1.3e6,
  db_backups_bytes: 2e6,
  projects: [
    {
      project_id: "p1",
      name: "Satisfactory",
      source_bytes: 200e6,
      analysis_bytes: 30e6,
      renders_bytes: 250e6,
      total_bytes: 480e6,
      last_activity: "2026-11-11T10:00:00Z",
    },
  ],
  retention: { temp_days: 3, render_days: 0, source_days: 0, auto: false },
  categories: {
    temp: "Fichiers intermédiaires (régénérables)",
    renders: "Shorts jamais exportés",
    sources: "Vidéos sources",
    db_backups: "Anciennes sauvegardes de migration de la base",
  },
};

const system = {
  app: "Gaming Shorts AI",
  version: "0.6.0",
  phase: "Phase 6",
  api_host: "127.0.0.1",
  api_port: 8000,
  data_dir: "D:/data",
  database_path: "D:/data/db",
  database_size_bytes: 1,
  disk_total_bytes: 10,
  disk_free_bytes: 5,
  data_dirs: [],
  tools: [],
  features: [],
  demo_step_seconds: 2,
  worker_stale_seconds: 30,
  gpu: null,
  asr: null,
  max_download_height: 1080,
  max_source_minutes: 240,
};

function settingsRoutes() {
  return mockFetch((c) => {
    if (c.url === "/api/system") return { body: system };
    if (c.url === "/api/settings/api") return { status: 500, body: { error: { message: "x" } } };
    if (c.url === "/api/settings/runtime" && c.method === "GET") return { body: runtime };
    if (c.url === "/api/settings/runtime" && c.method === "PUT") return { body: runtime };
    if (c.url === "/api/storage") return { body: storage };
    if (c.url === "/api/storage/cleanup") {
      const body = c.body as { categories: string[]; dry_run: boolean };
      return {
        body: {
          dry_run: body.dry_run,
          categories: body.categories,
          files: 1,
          bytes: 3_000_000,
          items: [
            {
              category: "temp",
              path: "projects/p1/renders/r1/audio_mix.wav",
              bytes: 3_000_000,
              reason: "fichier de travail d'un rendu terminé",
              project_id: "p1",
            },
          ],
          truncated: false,
          errors: [],
        },
      };
    }
    if (c.url === "/api/backups" && c.method === "GET") return { body: [] };
    if (c.url === "/api/backups" && c.method === "POST")
      return {
        status: 201,
        body: {
          name: "gsa-backup-20261111-170000.zip",
          size_bytes: 400_000,
          created_at: "2026-11-11T17:00:00Z",
          app_version: "0.6.0",
          schema_revision: "0006",
          counts: { projects: 1 },
          valid: true,
        },
      };
    return { body: health };
  });
}

describe("Paramètres (Phase 6)", () => {
  it("modifie un réglage global et signale les valeurs surchargées", async () => {
    const calls = settingsRoutes();
    const user = userEvent.setup();
    renderApp("/parametres");

    const form = await screen.findByRole("form", { name: "Réglages globaux" });
    expect(within(form).getByText("modifié")).toBeInTheDocument();
    const field = within(form).getByLabelText("Images envoyées par extrait");
    await user.clear(field);
    await user.type(field, "4");
    await user.click(within(form).getByRole("button", { name: "Enregistrer" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
        values: { frames_per_candidate: 4 },
      }),
    );
    await user.click(within(form).getByRole("button", { name: "Rétablir" }));
    await waitFor(() =>
      expect(calls.filter((c) => c.method === "PUT")[1]?.body).toEqual({
        values: { retention_temp_days: null },
      }),
    );
  });

  it("montre l'espace et n'efface qu'après aperçu et confirmation", async () => {
    const calls = settingsRoutes();
    const user = userEvent.setup();
    renderApp("/parametres");

    const card = await screen.findByLabelText("Stockage", { selector: "div" });
    expect(within(card).getByRole("link", { name: "Satisfactory" })).toHaveAttribute(
      "href",
      "/projets/p1",
    );
    expect(within(card).getByText("(3 j)")).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Voir ce qui peut être supprimé" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("projects/p1/renders/r1/audio_mix.wav")).toBeInTheDocument();
    const cleanups = () => calls.filter((c) => c.url === "/api/storage/cleanup");
    expect(cleanups().map((c) => (c.body as { dry_run: boolean }).dry_run)).toEqual([true]);
    await user.click(within(dialog).getByRole("button", { name: "Supprimer définitivement" }));
    await waitFor(() =>
      expect(cleanups()[1]?.body).toEqual({ categories: ["temp"], dry_run: false }),
    );
  });

  it("crée une sauvegarde", async () => {
    const calls = settingsRoutes();
    const user = userEvent.setup();
    renderApp("/parametres");
    const card = await screen.findByLabelText("Sauvegardes", { selector: "div" });
    expect(within(card).getByText(/Non inclus/)).toBeInTheDocument();
    await user.click(within(card).getByRole("button", { name: "Sauvegarder maintenant" }));
    await waitFor(() =>
      expect(calls.some((c) => c.url === "/api/backups" && c.method === "POST")).toBe(true),
    );
  });
});

describe("Pause d'un job", () => {
  it("met en pause un job en cours et reprend un job en pause", async () => {
    const running = makeJob({ id: "j1", status: "running", kind_label: "Import" });
    const paused = makeJob({ id: "j2", status: "paused", kind_label: "Analyse" });
    const calls = mockFetch((c) => {
      if (c.url.startsWith("/api/jobs?") || c.url === "/api/jobs")
        return { body: [running, paused] };
      if (c.url === "/api/jobs/j1/pause")
        return { body: { ...running, pause_requested: true, steps: [] } };
      if (c.url === "/api/jobs/j2/resume")
        return { body: { ...paused, status: "queued", steps: [] } };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/file");

    const runningCard = await screen.findByRole("article", { name: "Job Import" });
    await user.click(within(runningCard).getByRole("button", { name: "Pause" }));
    const pausedCard = screen.getByRole("article", { name: "Job Analyse" });
    expect(within(pausedCard).getByText("En pause")).toBeInTheDocument();
    expect(
      within(pausedCard).getByText(/Reprendre » remet le job dans la file/),
    ).toBeInTheDocument();
    await user.click(within(pausedCard).getByRole("button", { name: "Reprendre" }));
    await waitFor(() => {
      expect(calls.some((c) => c.url === "/api/jobs/j1/pause" && c.method === "POST")).toBe(true);
      expect(calls.some((c) => c.url === "/api/jobs/j2/resume" && c.method === "POST")).toBe(true);
    });
  });
});
