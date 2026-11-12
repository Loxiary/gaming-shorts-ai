import { useState } from "react";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ErrorBox, Loading } from "../../components/Feedback";
import { adminApi, useBackups, useCreateBackup, useDeleteBackup } from "../../services/adminApi";
import { errorMessage } from "../../services/api";
import { formatBytes, formatDate } from "../../services/format";

export function BackupsCard() {
  const backups = useBackups();
  const create = useCreateBackup();
  const remove = useDeleteBackup();
  const [toDelete, setToDelete] = useState<string | null>(null);

  return (
    <div className="card" aria-label="Sauvegardes">
      <header className="page-header">
        <h2>Sauvegardes</h2>
        <button
          type="button"
          className="btn btn-primary"
          disabled={create.isPending}
          onClick={() => create.mutate()}
        >
          {create.isPending ? "Sauvegarde…" : "Sauvegarder maintenant"}
        </button>
      </header>
      <p className="hint">
        Archive ZIP de la base (projets, transcriptions, analyses, rapports, coûts), des profils et
        des réglages. <strong>Non inclus</strong> : le fichier <code>.env</code> et la clé API, les
        vidéos, rendus, exports, modèles et musiques. Restauration (application arrêtée) :{" "}
        <code>python -m app.cli.backup restore &lt;archive&gt;</code> depuis le dossier backend.
      </p>
      {create.isError && <p className="job-error">{errorMessage(create.error)}</p>}
      {backups.isPending ? (
        <Loading />
      ) : backups.isError ? (
        <ErrorBox error={backups.error} />
      ) : backups.data.length === 0 ? (
        <p className="empty">Aucune sauvegarde.</p>
      ) : (
        <ul className="plain">
          {backups.data.map((b) => (
            <li key={b.name} className="backup-row">
              <a href={adminApi.backupUrl(b.name)} download={b.name}>
                {b.name}
              </a>{" "}
              <span className="muted">
                {formatBytes(b.size_bytes)} · {b.created_at ? formatDate(b.created_at) : "?"} ·
                schéma {b.schema_revision ?? "?"} · {b.counts.projects ?? "?"} projet(s)
              </span>
              {!b.valid && <span className="job-error"> archive illisible</span>}{" "}
              <button
                type="button"
                className="btn btn-small btn-danger"
                onClick={() => setToDelete(b.name)}
              >
                Supprimer
              </button>
            </li>
          ))}
        </ul>
      )}
      {toDelete && (
        <ConfirmDialog
          title="Supprimer cette sauvegarde ?"
          danger
          confirmLabel="Supprimer"
          pending={remove.isPending}
          onCancel={() => setToDelete(null)}
          onConfirm={() => remove.mutate(toDelete, { onSuccess: () => setToDelete(null) })}
          message={
            <p>
              <code>{toDelete}</code> sera supprimée définitivement.
            </p>
          }
        />
      )}
    </div>
  );
}
