import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { makeProjectDetail, makeRender } from "../test/renderFixtures";
import { health, mockFetch, renderApp } from "../test/utils";

describe("Publication et musique conseillée", () => {
  it("affiche le bandeau musique et les textes à copier", async () => {
    const render = makeRender({
      audience_language: "en",
      publication: {
        generated_by_ai: true,
        tiktok: { caption: "Ça part en vrille 😳 T'aurais fait quoi ?\n\n#gta6 #gaming" },
        youtube: { title: "Le vol qui tourne mal", description: "Contexte.\n\nSource : KVG" },
        context: "Contexte.",
        question: "T'aurais fait quoi ?",
        hashtags: ["#gta6", "#gaming"],
        credits: ["Source : « GTA V » — KVG"],
        music_suggestion: {
          mood: "tendu",
          genre: "trap",
          tempo: "rapide",
          search_keywords: ["dark trap", "tense"],
          why: "Poursuite nerveuse.",
          note: "À ajouter vous-même pendant l'upload.",
        },
        censored_words: 0,
      },
    });
    mockFetch((c) => {
      if (c.url === "/api/projects/p1") return { body: makeProjectDetail() };
      if (c.url === "/api/projects/p1/renders") return { body: [render] };
      if (c.url === "/api/profiles" || c.url === "/api/projects/p1/analyses") return { body: [] };
      if (c.url === "/api/job-kinds") return { body: [] };
      if (c.url.startsWith("/api/projects/p1/analysis-estimate"))
        return { status: 404, body: { error: { message: "x" } } };
      return { body: health };
    });
    const user = userEvent.setup();
    renderApp("/projets/p1");

    const card = await screen.findByRole("article", { name: "Short 0:30" });
    expect(within(card).getByText("English version")).toBeInTheDocument();
    const banner = within(card).getByRole("note", { name: "Musique à ajouter à l'upload" });
    expect(banner).toHaveTextContent("Rechercher : « dark trap », « tense »");
    await user.click(within(card).getByRole("tab", { name: "Publication" }));
    expect(within(card).getByLabelText("YouTube Shorts — titre")).toHaveValue(
      "Le vol qui tourne mal",
    );
    expect(within(card).getByLabelText("TikTok — légende")).toHaveValue(
      "Ça part en vrille 😳 T'aurais fait quoi ?\n\n#gta6 #gaming",
    );
    expect(within(card).getAllByRole("button", { name: "Copier" })).toHaveLength(3);
  });
});
