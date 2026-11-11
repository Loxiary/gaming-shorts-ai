import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { AudioStatus, MusicTrack } from "../services/musicApi";
import type { Render } from "../services/renderApi";
import { makeProjectDetail, makeRender } from "../test/renderFixtures";
import { health, mockFetch, renderApp } from "../test/utils";

const status: AudioStatus = {
  assets: [
    {
      id: "fr_FR-siwis-medium",
      label: "Français — SIWIS (femme)",
      purpose: "narration",
      size_mb: 63,
      license: "CC BY 4.0",
      credit: "Voix SIWIS",
      present: true,
      is_voice: true,
      language: "fr",
    },
    {
      id: "htdemucs",
      label: "Demucs v4",
      purpose: "music_separation",
      size_mb: 84,
      license: "MIT",
      credit: null,
      present: false,
      is_voice: false,
      language: null,
    },
  ],
  moods: ["énergique", "calme", "épique"],
  music_folder: "D:/GamingShortsAI/data/music",
  download_command: "python -m app.cli.models download --all",
};

function track(overrides: Partial<MusicTrack> = {}): MusicTrack {
  return {
    id: "m1",
    file_path: "music/calme.mp3",
    file_name: "calme.mp3",
    file_size_bytes: 3_000_000,
    duration_seconds: 125,
    title: "calme",
    artist: null,
    license: null,
    source_url: null,
    moods: [],
    notes: null,
    license_confirmed: false,
    usable: false,
    audio_url: "/api/music/m1/audio",
    ...overrides,
  };
}

describe("Bibliothèque musicale", () => {
  it("analyse le dossier, puis enregistre licence, ambiances et autorisation", async () => {
    let tracks: MusicTrack[] = [];
    const calls = mockFetch((c) => {
      if (c.url === "/api/audio/status") return { body: status };
      if (c.url === "/api/music/scan") {
        tracks = [track()];
        return {
          body: { added: 1, removed: 0, total: 1, errors: [], folder: status.music_folder },
        };
      }
      if (c.url === "/api/music" && c.method === "GET") return { body: tracks };
      if (c.url === "/api/music/m1" && c.method === "PATCH")
        return { body: track({ ...(c.body as object), usable: true }) };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/musique");

    expect(await screen.findByText(/Aucun morceau/)).toBeInTheDocument();
    expect(screen.getByText("D:/GamingShortsAI/data/music")).toBeInTheDocument();
    expect(screen.getByText("absent")).toBeInTheDocument(); // Demucs non installé
    expect(screen.getByText(status.download_command)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Analyser le dossier" }));
    expect(await screen.findByText(/1 morceau\(x\) ajouté\(s\)/)).toBeInTheDocument();
    const form = await screen.findByRole("form", { name: "Morceau calme.mp3" });
    expect(within(form).getByText("Licence à confirmer")).toBeInTheDocument();

    await user.type(within(form).getByLabelText(/Licence/), "CC BY 4.0");
    await user.type(within(form).getByLabelText("Artiste"), "Kevin");
    await user.click(within(form).getByLabelText("calme"));
    await user.click(within(form).getByLabelText(/Je confirme disposer de l'autorisation/));
    await user.click(within(form).getByRole("button", { name: "Enregistrer" }));

    await waitFor(() =>
      expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
        title: "calme",
        artist: "Kevin",
        license: "CC BY 4.0",
        source_url: null,
        moods: ["calme"],
        notes: null,
        license_confirmed: true,
      }),
    );
  });
});

const audioRender: Partial<Render> = {
  preview_audio_url: "/api/renders/r1/audio-preview",
  facecam: {
    status: "detected",
    crop: [0, 0, 0.75, 1],
    crop_side: "droite",
    loss: 0.25,
    presence: 0.9,
    warning: null,
  },
  audio_report: {
    source_music: {
      mode: "attenuate",
      status: "detected",
      attenuated: true,
      ratio: 0.48,
      reduction_db: 15,
      residual_ratio: 0.05,
      per_second: [0.9, 0.8, 0.1],
    },
    narration: {
      mode: "auto",
      status: "added",
      voice: "fr_FR-siwis-medium",
      reason: "Contexte utile.",
      lines: [{ t: 3, duration: 2, text: "Il lance la partie.", moved: true }],
    },
    music: { mode: "library", status: "added", title: "Calme", license: "CC BY 4.0" },
    levels: {},
    notes: ["Une remarque audio."],
  },
  credits: [{ kind: "music", text: "Musique : « Calme » (CC BY 4.0)" }],
};

describe("Audio et facecam d'un short", () => {
  it("affiche facecam, musique atténuée, narration, crédits et l'aperçu audio", async () => {
    mockFetch((c) => {
      if (c.url === "/api/projects/p1") return { body: makeProjectDetail() };
      if (c.url === "/api/projects/p1/renders") return { body: [makeRender(audioRender)] };
      if (c.url === "/api/profiles" || c.url === "/api/projects/p1/analyses") return { body: [] };
      if (c.url === "/api/job-kinds") return { body: [] };
      if (c.url.startsWith("/api/projects/p1/analysis-estimate"))
        return {
          body: {
            expected_candidates: 1,
            estimated_cost_usd: 0,
            key_configured: false,
            api_enabled: true,
            month_spent_usd: 0,
            monthly_cap_usd: 40,
            model: "m",
          },
        };
      return { body: health };
    });
    const user = userEvent.setup();
    const { container } = renderApp("/projets/p1");

    const card = await screen.findByRole("article", { name: "Short 0:30" });
    await user.click(within(card).getByRole("tab", { name: "Audio et facecam" }));
    expect(within(card).getByText("Facecam détecté et exclu par recadrage")).toBeInTheDocument();
    expect(within(card).getByText(/bord droite, 25 % de l'image retirée/)).toBeInTheDocument();
    expect(within(card).getByText(/sur 48 % de l'extrait · atténuée de 15 dB/)).toBeInTheDocument();
    expect(within(card).getByText(/« Il lance la partie. »/)).toBeInTheDocument();
    expect(within(card).getByText("(décalée dans un silence)")).toBeInTheDocument();
    expect(within(card).getByText("Musique : « Calme » (CC BY 4.0)")).toBeInTheDocument();
    expect(within(card).getByText("⚠ Une remarque audio.")).toBeInTheDocument();
    expect(
      within(card).getByRole("img", { name: /seconde par seconde \(3 s\)/ }),
    ).toBeInTheDocument();
    expect(container.querySelector("audio")?.getAttribute("src")).toBe(
      "/api/renders/r1/audio-preview",
    );
  });
});

describe("Réglages audio d'un profil", () => {
  it("propose les réglages audio et facecam et prévient si la voix ne parle pas la langue", async () => {
    const profile = {
      id: "pr1",
      name: "Profil",
      description: null,
      editorial_focus: null,
      threshold: 60,
      weights: {},
      output_language: "en",
      min_duration: 61,
      max_duration: 180,
      max_candidates: 12,
      use_vision: true,
      is_default: true,
      subtitle_mode: "source",
      subtitle_style: {
        font: "Arial Black",
        size: 76,
        text_color: "#FFFFFF",
        highlight_color: "#FFE500",
        keyword_color: "#38E1FF",
        uppercase: true,
        max_words: 3,
      },
      layout: "blur",
      zoom_intensity: 0.12,
      hook_enabled: true,
      cta_enabled: true,
      cta_text: null,
      render_encoder: "libx264",
      narration_mode: "auto",
      narration_voice: "fr_FR-siwis-medium",
      narration_speed: 1,
      narration_level_db: 0,
      game_level_db: 0,
      music_mode: "library",
      music_level_db: -18,
      source_music_mode: "attenuate",
      source_music_reduction_db: 15,
      facecam_mode: "crop",
      created_at: "2026-11-10T19:00:00Z",
      updated_at: "2026-11-10T19:00:00Z",
    };
    const calls = mockFetch((c) => {
      if (c.url === "/api/profiles" && c.method === "GET") return { body: [profile] };
      if (c.url === "/api/criteria") return { body: [] };
      if (c.url === "/api/audio/status") return { body: status };
      if (c.url === "/api/profiles/pr1" && c.method === "PUT") return { body: profile };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/profils");

    await user.click(await screen.findByRole("button", { name: "Modifier" }));
    expect(
      screen.getByText(/La voix choisie ne parle pas la langue du profil \(en\)/),
    ).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Musique d'origine"), "detect");
    expect(screen.getByLabelText(/Atténuation de la musique/)).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Facecam (webcam incrustée)"), "off");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => {
      const body = calls.find((c) => c.method === "PUT")?.body as Record<string, unknown>;
      expect(body.source_music_mode).toBe("detect");
      expect(body.facecam_mode).toBe("off");
      expect(body.music_level_db).toBe(-18);
    });
  });
});
