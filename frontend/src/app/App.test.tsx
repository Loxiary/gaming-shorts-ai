import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import {
  health,
  makeJob,
  makeProject,
  mockFetch,
  mockFetchOffline,
  renderApp,
} from "../test/utils";

describe("Layout et connexion backend", () => {
  it("affiche en permanence que l'IA et la vidéo ne sont pas implémentées", async () => {
    mockFetch((c) => (c.url === "/api/health" ? { body: health } : { body: [] }));
    renderApp("/");
    expect(screen.getByRole("note")).toHaveTextContent(/pas encore implémentés/);
    expect(await screen.findByText("Backend connecté")).toBeInTheDocument();
    expect(screen.getByText("Worker actif")).toBeInTheDocument();
  });

  it("signale un backend injoignable", async () => {
    mockFetchOffline();
    renderApp("/");
    expect(
      await screen.findByText("Backend injoignable", { selector: ".pill" }),
    ).toBeInTheDocument();
    expect(await screen.findByRole("alert")).toHaveTextContent(/start\.ps1/);
  });

  it("signale un worker arrêté", async () => {
    mockFetch((c) =>
      c.url === "/api/health"
        ? { body: { ...health, worker: { alive: false, last_seen_at: null, worker_id: null } } }
        : { body: [] },
    );
    renderApp("/");
    expect(await screen.findByText("Worker arrêté")).toBeInTheDocument();
  });
});

describe("Bibliothèque de projets", () => {
  it("liste les projets", async () => {
    mockFetch((c) =>
      c.url === "/api/projects"
        ? { body: [makeProject({ name: "GTA session 1" })] }
        : { body: health },
    );
    renderApp("/projets");
    expect(await screen.findByRole("link", { name: "GTA session 1" })).toHaveAttribute(
      "href",
      "/projets/p1",
    );
  });

  it("crée un projet de test puis ouvre sa fiche", async () => {
    const created = makeProject({ id: "new1", name: "Nouveau" });
    const calls = mockFetch((c) => {
      if (c.url === "/api/projects" && c.method === "POST") return { status: 201, body: created };
      if (c.url === "/api/projects") return { body: [] };
      if (c.url === "/api/projects/new1") return { body: { ...created, jobs: [] } };
      if (c.url === "/api/job-kinds") return { body: [] };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/projets");

    await user.click(await screen.findByRole("button", { name: "Nouveau projet" }));
    await user.click(screen.getByRole("button", { name: "Créer le projet" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Le nom du projet est obligatoire.");

    await user.type(screen.getByLabelText(/Nom du projet/), "Nouveau");
    await user.click(screen.getByRole("button", { name: "Créer le projet" }));

    expect(await screen.findByRole("heading", { level: 1, name: /Nouveau/ })).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST");
    expect(post?.body).toEqual({ name: "Nouveau", game: null, description: null, is_test: true });
  });
});

describe("Fiche projet", () => {
  const kinds = [
    { kind: "demo", label: "Démonstration", description: "Simulation", is_demo: true, steps: [] },
  ];

  it("ajoute un job de démonstration à la file", async () => {
    const calls = mockFetch((c) => {
      if (c.url === "/api/projects/p1") return { body: { ...makeProject(), jobs: [] } };
      if (c.url === "/api/job-kinds") return { body: kinds };
      if (c.url === "/api/jobs" && c.method === "POST")
        return { status: 201, body: { ...makeJob(), steps: [] } };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/projets/p1");
    await user.click(await screen.findByRole("button", { name: "Ajouter à la file" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        project_id: "p1",
        kind: "demo",
      }),
    );
  });

  it("exige une confirmation avant de supprimer", async () => {
    const calls = mockFetch((c) => {
      if (c.method === "DELETE") return { status: 204 };
      if (c.url === "/api/projects/p1") return { body: { ...makeProject(), jobs: [] } };
      if (c.url === "/api/projects") return { body: [] };
      if (c.url === "/api/job-kinds") return { body: kinds };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/projets/p1");

    await user.click(await screen.findByRole("button", { name: "Supprimer" }));
    const dialog = screen.getByRole("dialog");
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);

    await user.click(within(dialog).getByRole("button", { name: "Annuler" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE")).toBe(false);

    await user.click(screen.getByRole("button", { name: "Supprimer" }));
    await user.click(screen.getByRole("button", { name: "Supprimer définitivement" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "DELETE")?.url).toBe("/api/projects/p1?confirm=true"),
    );
    expect(
      await screen.findByRole("heading", { name: "Bibliothèque de projets" }),
    ).toBeInTheDocument();
  });

  it("affiche un message clair pour un projet introuvable", async () => {
    mockFetch((c) => (c.url === "/api/health" ? { body: health } : undefined));
    renderApp("/projets/absent");
    expect(await screen.findByRole("heading", { name: "Projet introuvable" })).toBeInTheDocument();
  });
});

describe("File d'attente", () => {
  it("affiche les jobs et propose uniquement les actions valides", async () => {
    const calls = mockFetch((c) => {
      if (c.url === "/api/jobs")
        return {
          body: [
            makeJob({ id: "a", status: "running", progress: 0.5 }),
            makeJob({ id: "b", status: "failed", error_message: "Échec simulé" }),
            makeJob({ id: "c", status: "completed", progress: 1 }),
          ],
        };
      if (c.method === "POST") return { body: { ...makeJob(), steps: [] } };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/file");

    const cards = await screen.findAllByRole("article");
    expect(cards).toHaveLength(3);
    const [running, failed, completed] = cards as [HTMLElement, HTMLElement, HTMLElement];

    expect(within(running).getByRole("progressbar")).toHaveAttribute("aria-valuenow", "50");
    expect(within(running).queryByRole("button", { name: "Relancer" })).not.toBeInTheDocument();
    expect(within(failed).getByText("Échec simulé")).toBeInTheDocument();
    expect(within(completed).queryByRole("button", { name: "Annuler" })).not.toBeInTheDocument();
    expect(within(completed).queryByRole("button", { name: "Relancer" })).not.toBeInTheDocument();

    await user.click(within(running).getByRole("button", { name: "Annuler" }));
    await user.click(within(failed).getByRole("button", { name: "Relancer" }));
    await waitFor(() => {
      const posts = calls.filter((c) => c.method === "POST").map((c) => c.url);
      expect(posts).toEqual(["/api/jobs/a/cancel", "/api/jobs/b/retry"]);
    });
  });

  it("filtre par statut", async () => {
    const calls = mockFetch((c) =>
      c.url.startsWith("/api/jobs") ? { body: [] } : { body: health },
    );
    const user = userEvent.setup();
    renderApp("/file");
    await user.click(await screen.findByRole("button", { name: "Échec" }));
    await waitFor(() => expect(calls.some((c) => c.url === "/api/jobs?status=failed")).toBe(true));
  });
});
