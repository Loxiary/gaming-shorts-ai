import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Analysis, Candidate, Profile } from "../services/analysisTypes";
import type { ProjectDetail } from "../services/types";
import { health, makeProject, mockFetch, renderApp } from "../test/utils";
import { DEFAULT_AUDIO, DEFAULT_EFFECTS } from "./audio/audioDefaults";

const CRITERIA = [
  { key: "hook", label: "Force de l'accroche" },
  { key: "entertainment", label: "Divertissement / intensité" },
];

const profile: Profile = {
  id: "pr1",
  name: "GTA 6 — Viral",
  description: "Moments forts.",
  editorial_focus: "Surprise",
  threshold: 65,
  weights: { hook: 1.6, entertainment: 1.3 },
  output_language: "fr",
  min_duration: 61,
  max_duration: 90,
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
  jump_zoom: true,
  progress_bar: true,
  mid_cta: true,
  reactions: true,
  zoom_intensity: 0.12,
  hook_enabled: true,
  cta_enabled: true,
  cta_text: null,
  render_encoder: "libx264",
  censor_profanity: true,
  min_confidence: 0.5,
  ...DEFAULT_AUDIO,
  ...DEFAULT_EFFECTS,
  created_at: "2026-11-10T19:00:00Z",
  updated_at: "2026-11-10T19:00:00Z",
};

function candidate(overrides: Partial<Candidate> = {}): Candidate {
  return {
    id: "c1",
    position: 0,
    start_seconds: 30,
    end_seconds: 120,
    duration_seconds: 90,
    peak_seconds: 50,
    signal_score: 0.8,
    status: "scored",
    summary: "Le joueur saute du pont en moto.",
    reason: "Cascade spectaculaire avec réaction.",
    events: [{ t: 52, description: "Saut" }],
    warnings: [],
    confidence: 0.8,
    overall_score: 82,
    selected: true,
    rejection_reason: null,
    error_message: null,
    transcript_excerpt: "Regarde ça !",
    scores: [{ criterion: "hook", label: "Force de l'accroche", score: 9, justification: "Fort" }],
    frames: [{ t: 31.5, url: "/api/candidates/c1/frames/0" }],
    signals: {},
    ...overrides,
  };
}

const analysis: Analysis = {
  id: "a1",
  project_id: "p1",
  job_id: "j9",
  profile_id: "pr1",
  profile_name: "GTA 6 — Viral",
  threshold: 65,
  engine: "llm",
  llm_model: "claude-sonnet-5-5",
  use_vision: true,
  notes: [],
  cost_usd: 0.123,
  created_at: "2026-11-10T19:10:00Z",
  candidate_count: 2,
  selected_count: 1,
  candidates: [
    candidate(),
    candidate({
      id: "c2",
      position: 1,
      start_seconds: 200,
      end_seconds: 290,
      overall_score: 40,
      selected: false,
      rejection_reason: "Sous le seuil (40 < 65)",
      status: "signals_only",
      warnings: ["Évaluation sans IA : notes approximatives."],
      summary: "Extrait calme.",
    }),
  ],
};

const estimate = {
  expected_candidates: 6,
  estimated_cost_usd: 0.174,
  key_configured: true,
  api_enabled: true,
  month_spent_usd: 1.5,
  monthly_cap_usd: 40,
  model: "claude-sonnet-5-5",
};

const system = {
  app: "Gaming Shorts AI",
  version: "0.3.0",
  phase: "Phase 3",
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

function project(): ProjectDetail {
  return {
    ...makeProject({ name: "Partie GTA" }),
    jobs: [],
    source: {
      id: "s1",
      source_type: "youtube",
      url: "https://www.youtube.com/watch?v=abcdefghijk",
      external_id: "abcdefghijk",
      rights_status: "owned",
      rights_note: null,
      title: "Partie GTA",
      uploader: "Moi",
      channel_url: null,
      upload_date: null,
      platform_license: null,
      duration_seconds: 600,
      media_available: true,
      media_size_bytes: 1000,
      audio_available: true,
      width: 1920,
      height: 1080,
      fps: 60,
      video_codec: "h264",
      audio_codec: "aac",
      has_audio: true,
      created_at: "2026-11-10T19:00:00Z",
    },
    transcript: {
      id: "t1",
      kind: "source",
      engine: "faster-whisper",
      model: "large-v3-turbo",
      device: "cuda",
      compute_type: "int8_float16",
      language: "fr",
      language_probability: 1,
      audio_duration_seconds: 600,
      processing_seconds: 20,
      segment_count: 0,
      created_at: "2026-11-10T19:05:00Z",
    },
    files_size_bytes: 100,
  };
}

function routes(extra: (url: string, method: string) => object | undefined = () => undefined) {
  return mockFetch((c) => {
    const custom = extra(c.url, c.method);
    if (custom) return custom;
    if (c.url === "/api/projects/p1") return { body: project() };
    if (c.url === "/api/profiles") return { body: [profile] };
    if (c.url === "/api/criteria") return { body: CRITERIA };
    if (c.url.startsWith("/api/projects/p1/analysis-estimate")) return { body: estimate };
    if (c.url === "/api/projects/p1/analyses" && c.method === "GET")
      return { body: [{ ...analysis, candidates: [] }] };
    if (c.url === "/api/analyses/a1") return { body: analysis };
    if (c.url === "/api/projects/p1/transcript")
      return { body: { ...project().transcript, segments: [] } };
    if (c.url === "/api/job-kinds") return { body: [] };
    return c.url.endsWith("/renders") ? { body: [] } : { body: health };
  });
}

describe("Détection des clips sur la fiche projet", () => {
  it("affiche l'estimation de coût et lance l'analyse avec le profil choisi", async () => {
    const calls = routes((url, method) =>
      url === "/api/projects/p1/analyses" && method === "POST"
        ? { status: 201, body: { ...analysis, candidates: [] } }
        : undefined,
    );
    const user = userEvent.setup();
    renderApp("/projets/p1");

    expect(await screen.findByText(/Coût IA estimé/)).toHaveTextContent("0,174 $");
    expect(screen.getByText(/Coût IA estimé/)).toHaveTextContent("40,00 $");
    await user.selectOptions(screen.getByLabelText("Évaluation"), "signals");
    expect(screen.getByText(/Aucun coût/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Lancer l'analyse" }));
    await waitFor(() =>
      expect(calls.find((c) => c.method === "POST")?.body).toEqual({
        profile_id: null,
        engine: "signals",
      }),
    );
  });

  it("liste les extraits classés avec notes, explications et avertissements", async () => {
    routes();
    const user = userEvent.setup();
    renderApp("/projets/p1");

    const cards = await screen.findAllByRole("article", { name: /Extrait/ });
    expect(cards).toHaveLength(2);
    const [best, weak] = cards as [HTMLElement, HTMLElement];
    expect(within(best).getByText("82")).toBeInTheDocument();
    expect(within(best).getByText("Sélectionné")).toBeInTheDocument();
    expect(within(best).getByText("Évalué par IA")).toBeInTheDocument();
    expect(within(best).getByText("Le joueur saute du pont en moto.")).toBeInTheDocument();
    expect(within(best).getByRole("img", { name: "Image à 0:31" })).toBeInTheDocument();
    expect(within(weak).getByText("Sous le seuil (40 < 65)")).toBeInTheDocument();
    expect(within(weak).getByText("Estimation sans IA")).toBeInTheDocument();
    expect(within(weak).getByText(/sans IA : notes approximatives/)).toBeInTheDocument();
    expect(screen.getByText(/pas des prédictions de vues/)).toBeInTheDocument();

    await user.click(within(best).getByRole("button", { name: "Détails" }));
    expect(within(best).getByLabelText("Force de l'accroche : 9 sur 10")).toBeInTheDocument();
    expect(within(best).getByText("Saut")).toBeInTheDocument();
  });

  it("change le seuil sans relancer l'analyse", async () => {
    const calls = routes((url) =>
      url === "/api/analyses/a1/reselect" ? { body: { ...analysis, threshold: 30 } } : undefined,
    );
    const user = userEvent.setup();
    renderApp("/projets/p1");
    const slider = await screen.findByRole("slider");
    const apply = screen.getByRole("button", { name: "Appliquer le seuil" });
    expect(apply).toBeDisabled();
    fireEvent.change(slider, { target: { value: "30" } });
    expect(apply).toBeEnabled();
    await user.click(apply);
    await waitFor(() =>
      expect(calls.find((c) => c.url === "/api/analyses/a1/reselect")?.body).toEqual({
        threshold: 30,
      }),
    );
  });
});

describe("Profils de montage", () => {
  it("liste, duplique et édite un profil", async () => {
    const calls = routes((url, method) => {
      if (url === "/api/profiles/pr1/duplicate") return { status: 201, body: profile };
      if (url === "/api/profiles/pr1" && method === "PUT") return { body: profile };
      return undefined;
    });
    const user = userEvent.setup();
    renderApp("/profils");

    const card = await screen.findByRole("article", { name: "Profil GTA 6 — Viral" });
    expect(within(card).getByText("Par défaut")).toBeInTheDocument();
    expect(within(card).queryByRole("button", { name: "Supprimer" })).not.toBeInTheDocument();
    expect(within(card).getByText(/Seuil 65\/100/)).toBeInTheDocument();

    await user.click(within(card).getByRole("button", { name: "Dupliquer" }));
    await waitFor(() =>
      expect(calls.some((c) => c.url === "/api/profiles/pr1/duplicate")).toBe(true),
    );

    await user.click(within(card).getByRole("button", { name: "Modifier" }));
    const name = screen.getByLabelText(/Nom/);
    await user.clear(name);
    await user.type(name, "Viral v2");
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => {
      const put = calls.find((c) => c.method === "PUT");
      expect(put?.body).toMatchObject({ name: "Viral v2", threshold: 65, min_duration: 61 });
    });
  });
});

describe("Coûts et réglages API", () => {
  it("affiche les dépenses et l'historique", async () => {
    routes((url) =>
      url === "/api/costs"
        ? {
            body: {
              month_spent_usd: 2.5,
              monthly_cap_usd: 40,
              total_spent_usd: 3,
              calls_this_month: 12,
              by_month: [{ month: "2026-11", cost_usd: 2.5, calls: 12 }],
              recent: [],
            },
          }
        : undefined,
    );
    renderApp("/couts");
    expect(await screen.findByText("Ce mois-ci (12 appels)")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "6");
    expect(screen.getByText("2026-11")).toBeInTheDocument();
  });

  it("modifie le plafond et l'autorisation d'appels payants", async () => {
    const apiSettings = {
      provider: "anthropic",
      model: "claude-sonnet-5-5",
      effort: "medium",
      key_configured: false,
      api_enabled: true,
      monthly_cap_usd: 40,
      month_spent_usd: 0,
      prices_per_mtok: { input: 2, output: 10, cache_read: 0.1, cache_write: 2.5 },
    };
    const calls = routes((url, method) => {
      if (url === "/api/settings/api")
        return { body: method === "PATCH" ? apiSettings : apiSettings };
      if (url === "/api/system") return { body: system };
      if (url === "/api/settings/runtime" || url === "/api/backups") return { body: [] };
      if (url === "/api/storage")
        return { status: 404, body: { error: { code: "not_found", message: "x" } } };
      return undefined;
    });
    const user = userEvent.setup();
    renderApp("/parametres");
    expect(await screen.findByText("Absente")).toBeInTheDocument();
    expect(screen.queryByText(/sk-ant/)).not.toBeInTheDocument();

    const cap = screen.getByLabelText("Plafond mensuel ($)");
    await user.clear(cap);
    await user.type(cap, "25");
    await user.click(screen.getByRole("button", { name: "Enregistrer le plafond" }));
    await user.click(screen.getByLabelText("Autoriser les appels payants à l'API"));
    await waitFor(() => {
      const patches = calls.filter((c) => c.method === "PATCH").map((c) => c.body);
      expect(patches).toEqual([{ monthly_cap_usd: 25 }, { api_enabled: false }]);
    });
  });
});
