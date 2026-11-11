import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import type { Render } from "../services/renderApi";
import { makeProjectDetail, makeRender } from "../test/renderFixtures";
import { health, mockFetch, renderApp } from "../test/utils";

const render = makeRender;
const project = makeProjectDetail;

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
