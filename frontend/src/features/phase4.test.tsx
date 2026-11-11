import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Render } from "../services/renderApi";
import type { ProjectDetail } from "../services/types";
import { health, makeProject, mockFetch, renderApp } from "../test/utils";

function render(overrides: Partial<Render> = {}): Render {
  return {
    id: "r1",
    project_id: "p1",
    candidate_id: "c1",
    job_id: "j1",
    job_status: "completed",
    job_error: null,
    start_seconds: 30,
    end_seconds: 120,
    duration_seconds: 90,
    profile_name: "GTA 6 — Viral",
    plan: {
      hook_text: "Une partie qui démarre fort",
      hook_kind: "original",
      hook_reason: "x",
      cta_text: "Tu aurais fait pareil ?",
      keywords: ["3000"],
      zooms: [{ t: 10, duration: 2, reason: "Explosion" }],
      warnings: [],
    },
    plan_engine: "llm",
    subtitles: [{ start: 0, end: 1, text: "Attention" }],
    subtitle_language: "fr",
    subtitles_are_translation: true,
    video_url: "/api/renders/r1/video",
    output_size_bytes: 25_000_000,
    qc: {
      passed: true,
      checks: [
        {
          key: "duration",
          label: "Durée entre 61 et 180 s",
          ok: true,
          detail: "90 s",
          level: "ok",
        },
        {
          key: "loudness",
          label: "Volume proche de -14 LUFS (±2)",
          ok: false,
          detail: "-18 LUFS",
          level: "warning",
        },
      ],
      measures: {},
    },
    qc_passed: true,
    risk_report: {
      source: {
        title: "Partie",
        creator: "Moi",
        url: "https://y/v",
        platform_license: "non indiquée",
      },
      rights: {
        status: "unknown",
        label: "Inconnu / non vérifié",
        note: null,
        verified_by_app: false,
      },
      audio_music: { status: "non_analysé", detail: "Musique non analysée (Phase 5)." },
      transformation: {
        level: "modérée",
        added: ["recadrage vertical 9:16", "accroche"],
        missing: ["narration originale"],
        detail: "",
      },
      reused_content: { level: "élevé", detail: "Droits non vérifiés." },
      facecam: { status: "non_vérifié", detail: "Facecam non vérifié (Phase 5)." },
      ai_warnings: [],
      qc_warnings: [],
      recommendations: ["Créditez la source."],
      blocking: false,
      disclaimer: "Ce rapport est une aide à la décision.",
    },
    export_warnings: [
      "Droits sur la source non vérifiés.",
      "Musique d'origine non analysée (Phase 5).",
    ],
    ready: true,
    cost_usd: 0.012,
    export_status: "not_exported",
    exported_path: null,
    export_confirmed_at: null,
    acknowledged_warnings: [],
    created_at: "2026-11-11T10:00:00Z",
    ...overrides,
  };
}

function project(): ProjectDetail {
  return {
    ...makeProject(),
    jobs: [],
    source: {
      id: "s1",
      source_type: "youtube",
      url: "https://y/v",
      external_id: "abcdefghijk",
      rights_status: "unknown",
      rights_note: null,
      title: "Partie",
      uploader: "Moi",
      channel_url: null,
      upload_date: null,
      platform_license: null,
      duration_seconds: 600,
      media_available: true,
      media_size_bytes: 1,
      audio_available: true,
      width: 1920,
      height: 1080,
      fps: 60,
      video_codec: "h264",
      audio_codec: "aac",
      has_audio: true,
      created_at: "2026-11-10T19:00:00Z",
    },
    transcript: null,
    files_size_bytes: 1,
  };
}

function routes(renders: Render[], extra: (url: string, method: string) => object | undefined) {
  return mockFetch((c) => {
    const custom = extra(c.url, c.method);
    if (custom) return custom;
    if (c.url === "/api/projects/p1") return { body: project() };
    if (c.url === "/api/projects/p1/renders") return { body: renders };
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
}

describe("Shorts montés", () => {
  it("affiche le short, son rapport de risques et son contrôle qualité", async () => {
    routes([render()], () => undefined);
    const user = userEvent.setup();
    const { container } = renderApp("/projets/p1");

    const card = await screen.findByRole("article", { name: "Short 0:30" });
    expect(container.querySelector("video.vertical")?.getAttribute("src")).toBe(
      "/api/renders/r1/video",
    );
    expect(within(card).getByText("Prêt à exporter")).toBeInTheDocument();
    expect(
      within(card).getByText(/Sous-titres traduits \(fr\) — traduction, pas verbatim/),
    ).toBeInTheDocument();
    expect(within(card).getByText("Risque élevé")).toBeInTheDocument();
    expect(within(card).getByText("Musique non analysée (Phase 5).")).toBeInTheDocument();

    await user.click(within(card).getByRole("tab", { name: "Contrôle qualité" }));
    expect(within(card).getByText(/-18 LUFS/)).toBeInTheDocument();
    await user.click(within(card).getByRole("tab", { name: "Plan éditorial" }));
    expect(within(card).getByText("Une partie qui démarre fort")).toBeInTheDocument();
    expect(within(card).getByText("texte original")).toBeInTheDocument();
  });

  it("exige de cocher la confirmation avant d'exporter, malgré les risques", async () => {
    const calls = routes([render()], (url) =>
      url === "/api/renders/r1/confirm-export"
        ? { body: render({ export_status: "exported", exported_path: "D:/exports/x.mp4" }) }
        : undefined,
    );
    const user = userEvent.setup();
    renderApp("/projets/p1");

    await user.click(await screen.findByRole("button", { name: "Exporter…" }));
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("⚠ Droits sur la source non vérifiés.")).toBeInTheDocument();
    const confirm = within(dialog).getByRole("button", {
      name: "Exporter malgré les avertissements",
    });
    expect(confirm).toBeDisabled();
    await user.click(within(dialog).getByLabelText(/J'ai lu ces avertissements/));
    expect(confirm).toBeEnabled();
    await user.click(confirm);
    await waitFor(() =>
      expect(calls.find((c) => c.url === "/api/renders/r1/confirm-export")?.body).toEqual({
        acknowledged: true,
      }),
    );
  });

  it("n'autorise pas l'export d'un rendu non prêt", async () => {
    routes(
      [
        render({
          ready: false,
          qc_passed: false,
          job_status: "failed",
          job_error: "Contrôle qualité échoué : Résolution 1080×1920 (9:16)",
        }),
      ],
      () => undefined,
    );
    renderApp("/projets/p1");
    expect(await screen.findByRole("button", { name: "Exporter…" })).toBeDisabled();
    expect(screen.getByText("Non exportable")).toBeInTheDocument();
    expect(screen.getByText(/Contrôle qualité échoué/)).toBeInTheDocument();
  });
});

describe("Page Exports", () => {
  it("liste les shorts exportés", async () => {
    routes([], (url) =>
      url === "/api/exports"
        ? {
            body: [
              render({
                export_status: "exported",
                exported_path: "D:/GamingShortsAI/data/exports/short.mp4",
                export_confirmed_at: "2026-11-11T11:00:00Z",
              }),
            ],
          }
        : undefined,
    );
    renderApp("/exports");
    expect(await screen.findByText("D:/GamingShortsAI/data/exports/short.mp4")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "0:30 → 2:00" })).toHaveAttribute(
      "href",
      "/projets/p1",
    );
  });
});
