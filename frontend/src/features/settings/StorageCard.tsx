import { useState } from "react";
import { Link } from "react-router";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ErrorBox, Loading } from "../../components/Feedback";
import { type CleanupResult, useCleanup, useStorage } from "../../services/adminApi";
import { errorMessage } from "../../services/api";
import { formatBytes, formatDate } from "../../services/format";

const DIR_LABELS: Record<string, string> = {
  sources: "Vidéos sources",
  projects: "Travail des projets (analyses, rendus)",
  exports: "Exports",
  models: "Modèles",
  music: "Musique",
  temp: "Temporaire",
  logs: "Journaux",
  backups: "Sauvegardes",
};

export function StorageCard() {
  const storage = useStorage();
  const preview = useCleanup();
  const run = useCleanup();
  const [selected, setSelected] = useState<string[]>(["temp"]);
  const [confirming, setConfirming] = useState<CleanupResult | null>(null);

  if (storage.isPending) return <Loading />;
  if (storage.isError) return <ErrorBox error={storage.error} />;
  const s = storage.data;
  const low = s.disk_free_bytes < s.min_free_disk_gb * 1e9 * 2;
  const days = (n: number) => (n > 0 ? `${n} j` : "jamais");
  const retention: Record<string, string> = {
    temp: days(s.retention.temp_days),
    renders: days(s.retention.render_days),
    sources: days(s.retention.source_days),
    db_backups: "garde la plus récente",
  };

  return (
    <div className="card" aria-label="Stockage">
      <h2>Stockage</h2>
      <p>
        <code>{s.data_dir}</code> — {formatBytes(s.disk_free_bytes)} libres sur{" "}
        {formatBytes(s.disk_total_bytes)}
        {low && (
          <span className="job-error">
            {" "}
            ⚠ espace faible (les imports s'arrêtent sous {s.min_free_disk_gb} Go)
          </span>
        )}
      </p>
      <dl className="details">
        {Object.entries(s.directories).map(([name, bytes]) => (
          <div key={name}>
            <dt>{DIR_LABELS[name] ?? name}</dt>
            <dd>{formatBytes(bytes)}</dd>
          </div>
        ))}
        <div>
          <dt>Base de données</dt>
          <dd>
            {formatBytes(s.database_bytes)}
            {s.db_backups_bytes > 0 &&
              ` (+ ${formatBytes(s.db_backups_bytes)} de sauvegardes de migration)`}
          </dd>
        </div>
      </dl>

      {s.projects.length > 0 && (
        <table className="usage-table">
          <caption>Espace par projet</caption>
          <thead>
            <tr>
              <th>Projet</th>
              <th>Source</th>
              <th>Analyses</th>
              <th>Rendus</th>
              <th>Total</th>
              <th>Dernière activité</th>
            </tr>
          </thead>
          <tbody>
            {s.projects.map((p) => (
              <tr key={p.project_id}>
                <td>
                  <Link to={`/projets/${p.project_id}`}>{p.name}</Link>
                </td>
                <td>{formatBytes(p.source_bytes)}</td>
                <td>{formatBytes(p.analysis_bytes)}</td>
                <td>{formatBytes(p.renders_bytes)}</td>
                <td>
                  <strong>{formatBytes(p.total_bytes)}</strong>
                </td>
                <td>{p.last_activity ? formatDate(p.last_activity) : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <fieldset className="moods">
        <legend>Nettoyage (délais réglables dans « Réglages globaux » &gt; Stockage)</legend>
        {Object.entries(s.categories).map(([key, label]) => (
          <label key={key} className="checkbox">
            <input
              type="checkbox"
              checked={selected.includes(key)}
              onChange={(e) =>
                setSelected((cur) =>
                  e.target.checked ? [...cur, key] : cur.filter((x) => x !== key),
                )
              }
            />
            {label} <span className="muted">({retention[key]})</span>
          </label>
        ))}
      </fieldset>
      <p className="hint">
        Jamais supprimés : exports, modèles, musique, journaux, base courante, ni les fichiers d'un
        projet dont un job est en attente, en cours ou en pause. Les fiches (transcriptions,
        analyses, rapports) sont conservées ; une vidéo source supprimée peut être retéléchargée.
      </p>
      <button
        type="button"
        className="btn"
        disabled={selected.length === 0 || preview.isPending}
        onClick={() =>
          preview.mutate(
            { categories: selected, dryRun: true },
            { onSuccess: (r) => setConfirming(r) },
          )
        }
      >
        {preview.isPending ? "Calcul…" : "Voir ce qui peut être supprimé"}
      </button>
      {preview.isError && <p className="job-error">{errorMessage(preview.error)}</p>}
      {run.data && !run.data.dry_run && (
        <p className="note" role="status">
          {run.data.files} élément(s) supprimé(s), {formatBytes(run.data.bytes)} libérés.
          {run.data.errors.map((e) => (
            <span key={e} className="job-error">
              {" "}
              ⚠ {e}
            </span>
          ))}
        </p>
      )}

      {confirming && (
        <ConfirmDialog
          title={
            confirming.files === 0
              ? "Rien à nettoyer"
              : `Supprimer ${confirming.files} élément(s) (${formatBytes(confirming.bytes)}) ?`
          }
          danger
          confirmLabel="Supprimer définitivement"
          confirmDisabled={confirming.files === 0}
          pending={run.isPending}
          onCancel={() => setConfirming(null)}
          onConfirm={() =>
            run.mutate(
              { categories: confirming.categories, dryRun: false },
              { onSuccess: () => setConfirming(null) },
            )
          }
          message={
            confirming.files === 0 ? (
              <p>Aucun fichier ne dépasse les délais de rétention choisis.</p>
            ) : (
              <>
                <p>Ces fichiers seront supprimés du disque (sans corbeille) :</p>
                <ul className="plain cleanup-list">
                  {confirming.items.map((i) => (
                    <li key={i.path}>
                      <code>{i.path}</code> — {formatBytes(i.bytes)}{" "}
                      <span className="muted">({i.reason})</span>
                    </li>
                  ))}
                </ul>
                {confirming.truncated && <p className="hint">Liste tronquée à 500 éléments.</p>}
              </>
            )
          }
        />
      )}
    </div>
  );
}
