import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { formatTimecode } from "../services/format";
import type { ProjectDetail, Source, Transcript } from "../services/types";
import { health, makeJob, makeProject, mockFetch, renderApp } from "../test/utils";

const source: Source = {
  id: "s1",
  source_type: "youtube",
  url: "https://www.youtube.com/watch?v=abcdefghijk",
  external_id: "abcdefghijk",
  rights_status: "unknown",
  rights_note: null,
  title: "Partie GTA",
  uploader: "Ma chaîne",
  channel_url: "https://www.youtube.com/@moi",
  upload_date: "20261101",
  platform_license: "Creative Commons Attribution license (reuse allowed)",
  duration_seconds: 125,
  media_available: true,
  media_size_bytes: 52_428_800,
  audio_available: true,
  width: 1920,
  height: 1080,
  fps: 60,
  video_codec: "h264",
  audio_codec: "aac",
  has_audio: true,
  created_at: "2026-11-10T19:00:00Z",
};

const transcript: Transcript = {
  id: "t1",
  kind: "source",
  engine: "faster-whisper 1.2.1",
  model: "large-v3-turbo",
  device: "cuda",
  compute_type: "int8_float16",
  language: "fr",
  language_probability: 0.99,
  audio_duration_seconds: 125,
  processing_seconds: 12,
  segment_count: 2,
  created_at: "2026-11-10T19:05:00Z",
  segments: [
    {
      position: 0,
      start_seconds: 0,
      end_seconds: 2.5,
      text: "Attention, il arrive par la gauche !",
      avg_logprob: -0.2,
      no_speech_prob: 0.01,
      words: [],
    },
    {
      position: 1,
      start_seconds: 65,
      end_seconds: 68,
      text: "On a réussi la mission.",
      avg_logprob: -0.1,
      no_speech_prob: 0.01,
      words: [],
    },
  ],
};

function detail(overrides: Partial<ProjectDetail> = {}): ProjectDetail {
  const { segments: _segments, ...summary } = transcript;
  void _segments;
  return {
    ...makeProject({ name: "Partie GTA", is_test: false }),
    jobs: [],
    source,
    transcript: summary,
    files_size_bytes: 60_000_000,
    ...overrides,
  };
}

describe("Import", () => {
  it("envoie les liens et le statut des droits, puis affiche le résultat par lien", async () => {
    const calls = mockFetch((c) => {
      if (c.url === "/api/imports")
        return {
          body: [
            {
              url: "https://youtu.be/abcdefghijk",
              status: "created",
              project_id: "p1",
              job_id: "j1",
              message: null,
            },
            {
              url: "https://vimeo.com/1",
              status: "rejected",
              project_id: null,
              job_id: null,
              message: "Seuls les liens YouTube sont pris en charge.",
            },
          ],
        };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/importer");

    await user.click(screen.getByRole("button", { name: "Importer le lien" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Collez au moins un lien");

    await user.type(
      screen.getByLabelText(/Liens YouTube/),
      "https://youtu.be/abcdefghijk{enter}https://vimeo.com/1",
    );
    await user.selectOptions(screen.getByLabelText(/Droits sur ces vidéos/), "owned");
    await user.type(screen.getByLabelText(/Jeu/), "GTA 6");
    await user.click(screen.getByRole("button", { name: "Importer 2 liens" }));

    expect(await screen.findByText("Ajouté à la file")).toBeInTheDocument();
    expect(screen.getByText(/Seuls les liens YouTube/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ouvrir le projet" })).toHaveAttribute(
      "href",
      "/projets/p1",
    );
    expect(calls.find((c) => c.url === "/api/imports")?.body).toEqual({
      urls: ["https://youtu.be/abcdefghijk", "https://vimeo.com/1"],
      rights_status: "owned",
      rights_note: null,
      game: "GTA 6",
    });
  });

  it("rappelle que les droits sont de la responsabilité de l'utilisateur", () => {
    mockFetch(() => ({ body: health }));
    renderApp("/importer");
    expect(screen.getAllByRole("note")[1]).toHaveTextContent(/ne donne pas le droit/);
  });
});

describe("Fiche projet avec source", () => {
  it("affiche la source, la transcription et permet de chercher dedans", async () => {
    mockFetch((c) => {
      if (c.url === "/api/projects/p1") return { body: detail() };
      if (c.url === "/api/projects/p1/transcript") return { body: transcript };
      if (c.url === "/api/job-kinds") return { body: [] };
      return { body: health };
    });
    const user = userEvent.setup();
    const { container } = renderApp("/projets/p1");

    expect(await screen.findByRole("link", { name: "Partie GTA" })).toHaveAttribute(
      "href",
      source.url,
    );
    expect(screen.getByText(/1920×1080/)).toBeInTheDocument();
    expect(screen.getByText(source.platform_license!)).toBeInTheDocument();
    expect(await screen.findByText("Attention, il arrive par la gauche !")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "1:05" })).toBeInTheDocument();
    expect(container.querySelector("video")?.getAttribute("src")).toBe("/api/projects/p1/media");

    await user.type(screen.getByLabelText("Rechercher dans la transcription"), "mission");
    expect(screen.queryByText("Attention, il arrive par la gauche !")).not.toBeInTheDocument();
    expect(screen.getByText("On a réussi la mission.")).toBeInTheDocument();
  });

  it("modifie la déclaration de droits sans rien bloquer", async () => {
    const calls = mockFetch((c) => {
      if (c.method === "PATCH") return { body: { ...source, rights_status: "authorized" } };
      if (c.url === "/api/projects/p1") return { body: detail({ transcript: null }) };
      if (c.url === "/api/job-kinds") return { body: [] };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/projets/p1");
    await user.selectOptions(await screen.findByLabelText("Droits déclarés"), "authorized");
    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")).toMatchObject({
        url: "/api/projects/p1/source",
        body: { rights_status: "authorized" },
      }),
    );
    expect(screen.getByText(/Pas encore de transcription/)).toBeInTheDocument();
  });

  it("annonce la taille des fichiers supprimés avec le projet", async () => {
    mockFetch((c) => {
      if (c.url === "/api/projects/p1") return { body: detail({ transcript: null }) };
      if (c.url === "/api/job-kinds") return { body: [] };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/projets/p1");
    await user.click(await screen.findByRole("button", { name: "Supprimer" }));
    expect(within(screen.getByRole("dialog")).getByText(/57,2 Mo/)).toBeInTheDocument();
  });
});

describe("Progression détaillée", () => {
  it("affiche l'étape courante et son détail", async () => {
    mockFetch((c) => {
      if (c.url === "/api/jobs")
        return {
          body: [
            makeJob({
              kind: "ingest_youtube",
              kind_label: "Import YouTube et transcription",
              is_demo: false,
              status: "running",
              progress: 0.3,
              current_step: "downloading",
              current_step_label: "Téléchargement",
              current_step_detail: "45 Mo / 120 Mo",
            }),
          ],
        };
      return { body: health };
    });
    renderApp("/file");
    expect(await screen.findByText("Téléchargement")).toBeInTheDocument();
    expect(screen.getByText(/45 Mo \/ 120 Mo/)).toBeInTheDocument();
    expect(screen.queryByText("Démo")).not.toBeInTheDocument();
  });

  it("formate les timecodes", () => {
    expect(formatTimecode(0)).toBe("0:00");
    expect(formatTimecode(65.4)).toBe("1:05");
    expect(formatTimecode(3725)).toBe("1:02:05");
    expect(formatTimecode(null)).toBe("—");
  });
});
