import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeProjectDetail, makeRender } from "../test/renderFixtures";
import { health, mockFetch, renderApp } from "../test/utils";
import { DEFAULT_AUDIO, DEFAULT_EFFECTS } from "./audio/audioDefaults";

const estimate = {
  expected_candidates: 1,
  estimated_cost_usd: 0,
  key_configured: false,
  api_enabled: true,
  month_spent_usd: 0,
  monthly_cap_usd: 40,
  model: "m",
};

describe("Transitions et effets (Phase 7)", () => {
  it("affiche les effets du plan et les bruitages du mixage", async () => {
    const base = makeRender();
    const render = makeRender({
      plan: {
        ...base.plan!,
        effects: [
          { t: 6, kind: "flash", duration: 0.3, reason: "Révélation de l'usine" },
          { t: 12, kind: "shake", duration: 0.6, reason: "Explosion" },
        ],
      },
      audio_report: {
        source_music: { mode: "off", status: "disabled", attenuated: false },
        narration: { mode: "off", status: "disabled", lines: [] },
        music: { mode: "off", status: "disabled" },
        sfx: {
          mode: "auto",
          status: "added",
          level_db: -14,
          events: [
            { t: 0.3, kind: "whoosh" },
            { t: 12, kind: "impact" },
          ],
        },
        levels: {},
        notes: [],
      },
    });
    mockFetch((c) => {
      if (c.url === "/api/projects/p1") return { body: makeProjectDetail() };
      if (c.url === "/api/projects/p1/renders") return { body: [render] };
      if (c.url === "/api/profiles" || c.url === "/api/projects/p1/analyses") return { body: [] };
      if (c.url === "/api/job-kinds") return { body: [] };
      if (c.url.startsWith("/api/projects/p1/analysis-estimate")) return { body: estimate };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/projets/p1");

    const card = await screen.findByRole("article", { name: "Short 0:30" });
    await user.click(within(card).getByRole("tab", { name: "Plan éditorial" }));
    expect(
      within(card).getByText(
        "Flash à 0:06 (Révélation de l'usine) · Tremblement à 0:12 (Explosion)",
      ),
    ).toBeInTheDocument();
    await user.click(within(card).getByRole("tab", { name: "Audio et facecam" }));
    expect(
      within(card).getByText(
        /2 bruitage\(s\) synthétisé\(s\) à -14 dB : souffle 0:00, impact 0:12/,
      ),
    ).toBeInTheDocument();
  });

  it("règle transitions et effets dans un profil", async () => {
    const profile = {
      id: "pr1",
      name: "Profil",
      description: null,
      editorial_focus: null,
      threshold: 60,
      weights: {},
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
      zoom_intensity: 0.12,
      hook_enabled: true,
      cta_enabled: true,
      cta_text: null,
      render_encoder: "libx264",
      censor_profanity: true,
      ...DEFAULT_AUDIO,
      ...DEFAULT_EFFECTS,
      created_at: "2026-11-10T19:00:00Z",
      updated_at: "2026-11-10T19:00:00Z",
    };
    const calls = mockFetch((c) => {
      if (c.url === "/api/profiles" && c.method === "GET") return { body: [profile] };
      if (c.url === "/api/criteria") return { body: [] };
      if (c.url === "/api/audio/status") return { status: 404, body: { error: { message: "x" } } };
      if (c.url === "/api/profiles/pr1" && c.method === "PUT") return { body: profile };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/profils");

    await user.click(await screen.findByRole("button", { name: "Modifier" }));
    await user.selectOptions(screen.getByLabelText("Transition d'entrée"), "fade");
    await user.selectOptions(screen.getByLabelText("Bruitages"), "off");
    expect(screen.getByLabelText(/Niveau des bruitages/)).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Effets (flash, tremblement)"), "off");
    expect(screen.getByLabelText(/Durée max/)).toHaveAttribute("max", "90");
    await user.click(screen.getByLabelText(/Masquer les mots grossiers/));
    await user.click(screen.getByRole("button", { name: "Enregistrer" }));
    await waitFor(() => {
      const body = calls.find((c) => c.method === "PUT")?.body as Record<string, unknown>;
      expect(body).toMatchObject({
        transition_in: "fade",
        transition_out: "fade",
        sfx_mode: "off",
        effects_mode: "off",
        censor_profanity: false,
      });
    });
  });
});
