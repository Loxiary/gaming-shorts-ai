import { useState } from "react";

import { ErrorBox, Loading } from "../../components/Feedback";
import { errorMessage } from "../../services/api";
import { formatBytes, formatTimecode } from "../../services/format";
import {
  type MusicTrack,
  type MusicTrackInput,
  useAudioStatus,
  useMusic,
  useScanMusic,
  useUpdateMusic,
} from "../../services/musicApi";

export function MusicPage() {
  const tracks = useMusic();
  const status = useAudioStatus();
  const scan = useScanMusic();

  return (
    <section>
      <header className="page-header">
        <h1>Musique et modèles audio</h1>
        <button
          type="button"
          className="btn btn-primary"
          disabled={scan.isPending}
          onClick={() => scan.mutate()}
        >
          {scan.isPending ? "Analyse…" : "Analyser le dossier"}
        </button>
      </header>
      <p className="hint">
        L'application ne télécharge aucune musique. Déposez vos morceaux (mp3, wav, flac, ogg, m4a)
        dans <code>{status.data?.music_folder ?? "le dossier music des données"}</code>, analysez le
        dossier, puis renseignez la licence de chaque morceau. Seuls les morceaux dont vous
        confirmez l'autorisation sont utilisés dans les shorts, et leur crédit est ajouté au rapport
        et à la fiche d'export.
      </p>
      {scan.isError && <p className="job-error">{errorMessage(scan.error)}</p>}
      {scan.data && (
        <p className="note" role="status">
          {scan.data.added} morceau(x) ajouté(s), {scan.data.removed} retiré(s), {scan.data.total}{" "}
          au total.
          {scan.data.errors.map((e) => (
            <span key={e} className="job-error">
              {" "}
              ⚠ {e}
            </span>
          ))}
        </p>
      )}

      {tracks.isPending ? (
        <Loading />
      ) : tracks.isError ? (
        <ErrorBox error={tracks.error} onRetry={() => tracks.refetch()} />
      ) : tracks.data.length === 0 ? (
        <p className="empty">Aucun morceau. Déposez des fichiers puis analysez le dossier.</p>
      ) : (
        <div className="music-list">
          {tracks.data.map((t) => (
            <TrackEditor key={t.id} track={t} moods={status.data?.moods ?? []} />
          ))}
        </div>
      )}

      <h2>Modèles locaux</h2>
      {status.data && (
        <>
          <ul className="plain">
            {status.data.assets.map((a) => (
              <li key={a.id}>
                <span className={`badge ${a.present ? "badge-completed" : "badge-failed"}`}>
                  {a.present ? "installé" : "absent"}
                </span>{" "}
                {a.label}{" "}
                <span className="muted">
                  — ~{a.size_mb} Mo — {a.license}
                </span>
              </li>
            ))}
          </ul>
          {status.data.assets.some((a) => !a.present) && (
            <p className="hint">
              Installation (taille et licence affichées, confirmation demandée) :{" "}
              <code>{status.data.download_command}</code> depuis le dossier backend.
            </p>
          )}
        </>
      )}
    </section>
  );
}

function TrackEditor({ track, moods }: { track: MusicTrack; moods: string[] }) {
  const update = useUpdateMusic();
  const [data, setData] = useState<MusicTrackInput>({
    title: track.title,
    artist: track.artist,
    license: track.license,
    source_url: track.source_url,
    moods: track.moods,
    notes: track.notes,
    license_confirmed: track.license_confirmed,
  });
  const set = <K extends keyof MusicTrackInput>(k: K, v: MusicTrackInput[K]) =>
    setData((d) => ({ ...d, [k]: v }));
  const text = (k: "title" | "artist" | "license" | "source_url") => ({
    value: data[k] ?? "",
    onChange: (e: React.ChangeEvent<HTMLInputElement>) => set(k, e.target.value || null),
  });

  return (
    <form
      className="card music-track"
      aria-label={`Morceau ${track.file_name}`}
      onSubmit={(e) => {
        e.preventDefault();
        update.mutate({ id: track.id, data });
      }}
    >
      <header className="page-header">
        <h3>{track.file_name}</h3>
        <span className={`badge ${track.usable ? "badge-completed" : "badge-cancelled"}`}>
          {track.usable ? "Utilisable" : "Licence à confirmer"}
        </span>
      </header>
      <p className="hint">
        {track.duration_seconds ? formatTimecode(track.duration_seconds) : "?"}
        {track.file_size_bytes ? ` · ${formatBytes(track.file_size_bytes)}` : ""}
      </p>
      <audio controls preload="none" src={track.audio_url} />
      <div className="form-grid">
        <label>
          Titre
          <input maxLength={300} {...text("title")} />
        </label>
        <label>
          Artiste
          <input maxLength={300} {...text("artist")} />
        </label>
        <label>
          Licence (ex. CC BY 4.0, licence achetée…)
          <input maxLength={300} {...text("license")} />
        </label>
        <label>
          Source (adresse)
          <input type="url" maxLength={500} {...text("source_url")} />
        </label>
      </div>
      <fieldset className="moods">
        <legend>Ambiances</legend>
        {moods.map((m) => (
          <label key={m} className="checkbox">
            <input
              type="checkbox"
              checked={data.moods.includes(m)}
              onChange={(e) =>
                set(
                  "moods",
                  e.target.checked ? [...data.moods, m] : data.moods.filter((x) => x !== m),
                )
              }
            />
            {m}
          </label>
        ))}
      </fieldset>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.license_confirmed}
          onChange={(e) => set("license_confirmed", e.target.checked)}
        />
        Je confirme disposer de l'autorisation d'utiliser ce morceau dans mes shorts
      </label>
      {update.isError && <p className="job-error">{errorMessage(update.error)}</p>}
      <div className="form-actions">
        <button type="submit" className="btn btn-primary" disabled={update.isPending}>
          {update.isPending ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>
    </form>
  );
}
