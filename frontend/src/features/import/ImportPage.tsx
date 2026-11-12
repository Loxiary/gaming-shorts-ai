import { useState } from "react";
import { Link } from "react-router";

import { errorMessage } from "../../services/api";
import { RIGHTS_LABELS } from "../../services/format";
import { useImportSources } from "../../services/queries";
import type { RightsStatus } from "../../services/types";

const RESULT_LABELS = {
  created: "Ajouté à la file",
  duplicate: "Déjà dans la bibliothèque",
  rejected: "Refusé",
} as const;

export function ImportPage() {
  const [urls, setUrls] = useState("");
  const [rights, setRights] = useState<RightsStatus>("unknown");
  const [note, setNote] = useState("");
  const [game, setGame] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const importer = useImportSources();

  const lines = urls
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter(Boolean);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (lines.length === 0) {
      setLocalError("Collez au moins un lien YouTube.");
      return;
    }
    if (lines.length > 20) {
      setLocalError("20 liens maximum par import.");
      return;
    }
    setLocalError(null);
    importer.mutate(
      { urls: lines, rights_status: rights, rights_note: note || null, game: game || null },
      { onSuccess: (results) => results.every((r) => r.status !== "rejected") && setUrls("") },
    );
  };

  const error = localError ?? (importer.error ? errorMessage(importer.error) : null);

  return (
    <section>
      <h1>Importer des vidéos</h1>
      <p className="muted">
        Collez un lien YouTube par ligne. Chaque vidéo devient un projet de la bibliothèque et passe
        dans la file : validation, téléchargement, analyse technique, extraction de l'audio puis
        transcription locale.
      </p>

      <div className="alert alert-warn" role="note">
        <span>
          Importer une vidéo ne donne pas le droit de la réutiliser. N'importez que des vidéos dont
          vous détenez les droits ou pour lesquelles vous avez une autorisation. Seules les vidéos
          publiques ou non répertoriées sont prises en charge : aucun contournement de restriction
          (compte, âge, DRM, géoblocage).
        </span>
      </div>

      <div className="card">
        <form className="form form-wide" onSubmit={submit} noValidate>
          <label>
            Liens YouTube (un par ligne, 20 maximum)
            <textarea
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              rows={6}
              placeholder={"https://www.youtube.com/watch?v=…\nhttps://youtu.be/…"}
              spellCheck={false}
            />
          </label>
          <label>
            Droits sur ces vidéos (déclaration informative)
            <select value={rights} onChange={(e) => setRights(e.target.value as RightsStatus)}>
              {(Object.keys(RIGHTS_LABELS) as RightsStatus[]).map((r) => (
                <option key={r} value={r}>
                  {RIGHTS_LABELS[r]}
                </option>
              ))}
            </select>
            <span className="hint">
              Ce choix est enregistré pour le rapport de risques ; il ne bloque aucun traitement.
              Vous pourrez le modifier projet par projet.
            </span>
          </label>
          <label>
            Précisions sur les droits (facultatif)
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              maxLength={2000}
              placeholder="Ex. accord écrit du créateur le 10/11/2026"
            />
          </label>
          <label>
            Jeu (facultatif)
            <input
              value={game}
              onChange={(e) => setGame(e.target.value)}
              maxLength={120}
              placeholder="Ex. GTA 6"
            />
          </label>
          {error && (
            <p className="job-error" role="alert">
              {error}
            </p>
          )}
          <div className="form-actions">
            <button type="submit" className="btn btn-primary" disabled={importer.isPending}>
              {importer.isPending
                ? "Import…"
                : `Importer ${lines.length > 1 ? `${lines.length} liens` : "le lien"}`}
            </button>
          </div>
        </form>
      </div>

      {importer.data && (
        <div className="card">
          <h2>Résultat</h2>
          <ul className="plain">
            {importer.data.map((r) => (
              <li key={r.url} className="import-result">
                <span
                  className={
                    r.status === "created"
                      ? "badge badge-completed"
                      : r.status === "duplicate"
                        ? "badge badge-cancelled"
                        : "badge badge-failed"
                  }
                >
                  {RESULT_LABELS[r.status]}
                </span>{" "}
                <code>{r.url}</code>
                {r.message && <span className="muted"> — {r.message}</span>}
                {r.project_id && (
                  <>
                    {" "}
                    <Link to={`/projets/${r.project_id}`}>Ouvrir le projet</Link>
                  </>
                )}
              </li>
            ))}
          </ul>
          <p className="muted">
            Suivez l'avancement dans la <Link to="/file">file d'attente</Link>.
          </p>
        </div>
      )}
    </section>
  );
}
