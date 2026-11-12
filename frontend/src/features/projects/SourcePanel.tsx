import { useState } from "react";

import { errorMessage } from "../../services/api";
import { formatBytes, formatTimecode, RIGHTS_LABELS } from "../../services/format";
import { useCreateJob, useUpdateSource } from "../../services/queries";
import type { RightsStatus, Source } from "../../services/types";

function formatUploadDate(value: string | null): string {
  if (!value || value.length !== 8) return "—";
  return `${value.slice(6, 8)}/${value.slice(4, 6)}/${value.slice(0, 4)}`;
}

export function SourcePanel({ projectId, source }: { projectId: string; source: Source }) {
  const update = useUpdateSource(projectId);
  const [note, setNote] = useState(source.rights_note ?? "");

  return (
    <div className="card">
      <h2>Source</h2>
      <dl className="details">
        <div>
          <dt>Vidéo</dt>
          <dd>
            <a href={source.url} target="_blank" rel="noreferrer noopener">
              {source.title ?? source.url}
            </a>
          </dd>
        </div>
        <div>
          <dt>Créateur</dt>
          <dd>
            {source.channel_url ? (
              <a href={source.channel_url} target="_blank" rel="noreferrer noopener">
                {source.uploader ?? source.channel_url}
              </a>
            ) : (
              (source.uploader ?? "—")
            )}
          </dd>
        </div>
        <div>
          <dt>Publiée le</dt>
          <dd>{formatUploadDate(source.upload_date)}</dd>
        </div>
        <div>
          <dt>Licence indiquée par YouTube</dt>
          <dd>{source.platform_license ?? "—"}</dd>
        </div>
        <div>
          <dt>Durée</dt>
          <dd>{formatTimecode(source.duration_seconds)}</dd>
        </div>
        <div>
          <dt>Fichier</dt>
          <dd>
            {source.media_available ? (
              <>
                {source.width}×{source.height}
                {source.fps ? ` · ${source.fps} i/s` : ""} · {source.video_codec ?? "?"}/
                {source.audio_codec ?? "?"} ·{" "}
                {source.media_size_bytes ? formatBytes(source.media_size_bytes) : "—"}
              </>
            ) : (
              <RedownloadSource projectId={projectId} />
            )}
          </dd>
        </div>
      </dl>

      <div className="rights">
        <label>
          Droits déclarés
          <select
            value={source.rights_status}
            disabled={update.isPending}
            onChange={(e) => update.mutate({ rights_status: e.target.value as RightsStatus })}
          >
            {(Object.keys(RIGHTS_LABELS) as RightsStatus[]).map((r) => (
              <option key={r} value={r}>
                {RIGHTS_LABELS[r]}
              </option>
            ))}
          </select>
        </label>
        <label>
          Précisions
          <input
            value={note}
            maxLength={2000}
            onChange={(e) => setNote(e.target.value)}
            onBlur={() => {
              if (note !== (source.rights_note ?? "")) update.mutate({ rights_note: note || null });
            }}
            placeholder="Ex. accord écrit du créateur"
          />
        </label>
        <p className="hint">
          Information conservée pour le futur rapport de risques. Elle ne bloque aucun traitement et
          ne garantit pas que la réutilisation est autorisée.
        </p>
        {update.isError && <p className="job-error">{errorMessage(update.error)}</p>}
      </div>
    </div>
  );
}

function RedownloadSource({ projectId }: { projectId: string }) {
  const createJob = useCreateJob();
  return (
    <>
      <span className="muted">non disponible (pas encore téléchargée ou supprimée)</span>{" "}
      <button
        type="button"
        className="btn btn-small"
        disabled={createJob.isPending || createJob.isSuccess}
        onClick={() => createJob.mutate({ projectId, kind: "ingest_youtube" })}
        title="Relance l'import : téléchargement et transcription"
      >
        {createJob.isSuccess ? "Import ajouté à la file" : "Retélécharger la vidéo"}
      </button>
      {createJob.isError && <span className="job-error"> {errorMessage(createJob.error)}</span>}
    </>
  );
}
