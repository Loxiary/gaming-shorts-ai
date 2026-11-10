import { ErrorBox, Loading } from "../../components/Feedback";
import { formatBytes } from "../../services/format";
import { useSystem } from "../../services/queries";

export function SettingsPage() {
  const system = useSystem();

  if (system.isPending) return <Loading />;
  if (system.isError) return <ErrorBox error={system.error} onRetry={() => system.refetch()} />;
  const s = system.data;

  return (
    <section>
      <h1>Paramètres</h1>
      <p className="muted">
        Configuration en lecture seule. Pour la modifier, éditez le fichier <code>.env</code> à la
        racine du projet puis redémarrez l'application (<code>scripts\stop.ps1</code> puis{" "}
        <code>scripts\start.ps1</code>).
      </p>

      <div className="card">
        <h2>Application</h2>
        <dl className="details">
          <div>
            <dt>Version</dt>
            <dd>
              {s.app} {s.version} — {s.phase}
            </dd>
          </div>
          <div>
            <dt>API locale</dt>
            <dd>
              <code>
                http://{s.api_host}:{s.api_port}
              </code>{" "}
              (accessible uniquement depuis ce PC)
            </dd>
          </div>
          <div>
            <dt>Durée d'une étape de démo</dt>
            <dd>{s.demo_step_seconds} s</dd>
          </div>
          <div>
            <dt>Reprise d'un job abandonné après</dt>
            <dd>{s.worker_stale_seconds} s sans signe de vie du worker</dd>
          </div>
          <div>
            <dt>Import YouTube</dt>
            <dd>
              {s.max_download_height}p maximum, vidéos de {s.max_source_minutes} min maximum
            </dd>
          </div>
        </dl>
      </div>

      <div className="card">
        <h2>Transcription et GPU</h2>
        <dl className="details">
          {s.asr && (
            <>
              <div>
                <dt>Modèle</dt>
                <dd>
                  {s.asr.engine} · {s.asr.model}{" "}
                  {s.asr.model_present ? (
                    <span className="badge badge-completed">Installé</span>
                  ) : (
                    <span className="badge badge-failed">Absent</span>
                  )}
                  <br />
                  <code>{s.asr.model_dir}</code>
                </dd>
              </div>
              <div>
                <dt>Exécution</dt>
                <dd>
                  appareil {s.asr.device}, précision {s.asr.compute_type}, langue {s.asr.language},
                  filtre de voix (VAD) {s.asr.vad ? "activé" : "désactivé"}
                </dd>
              </div>
            </>
          )}
          <div>
            <dt>GPU</dt>
            <dd>
              {s.gpu ? (
                <>
                  {s.gpu.name} — VRAM utilisée {s.gpu.memory_used_mib} / {s.gpu.memory_total_mib}{" "}
                  Mio (libre {s.gpu.memory_free_mib} Mio), pilote {s.gpu.driver_version}
                </>
              ) : (
                "Aucun GPU NVIDIA détecté : la transcription utilisera le CPU."
              )}
            </dd>
          </div>
        </dl>
        {s.asr && !s.asr.model_present && (
          <p className="job-error">
            Modèle absent : la transcription échouera. Téléchargez-le avec{" "}
            <code>cd backend; .\.venv\Scripts\python.exe -m app.cli.models download</code>
          </p>
        )}
      </div>

      <div className="card">
        <h2>Stockage local</h2>
        <dl className="details">
          <div>
            <dt>Dossier de données</dt>
            <dd>
              <code>{s.data_dir}</code>
            </dd>
          </div>
          <div>
            <dt>Base SQLite</dt>
            <dd>
              <code>{s.database_path}</code> ({formatBytes(s.database_size_bytes)})
            </dd>
          </div>
          <div>
            <dt>Espace libre sur le disque</dt>
            <dd>
              {formatBytes(s.disk_free_bytes)} sur {formatBytes(s.disk_total_bytes)}
            </dd>
          </div>
        </dl>
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Dossier</th>
                <th>Chemin</th>
                <th>Taille</th>
              </tr>
            </thead>
            <tbody>
              {s.data_dirs.map((d) => (
                <tr key={d.name}>
                  <td>{d.name}</td>
                  <td>
                    <code>{d.path}</code>
                  </td>
                  <td>{d.exists ? formatBytes(d.size_bytes) : "absent"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="card">
        <h2>Outils détectés</h2>
        <p className="muted">
          FFmpeg et ffprobe sont utilisés pour l'analyse technique et l'extraction de l'audio.
        </p>
        <ul className="plain">
          {s.tools.map((t) => (
            <li key={t.name}>
              <span className={t.found ? "badge badge-completed" : "badge badge-failed"}>
                {t.found ? "Trouvé" : "Absent"}
              </span>{" "}
              <strong>{t.name}</strong> {t.path && <code>{t.path}</code>}
            </li>
          ))}
        </ul>
      </div>

      <div className="card">
        <h2>Fonctionnalités</h2>
        <ul className="plain">
          {s.features.map((f) => (
            <li key={f.name}>
              <span className={f.available ? "badge badge-completed" : "badge badge-cancelled"}>
                {f.available ? "Disponible" : "Non disponible"}
              </span>{" "}
              <strong>{f.name}</strong> <span className="muted">— {f.note}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
