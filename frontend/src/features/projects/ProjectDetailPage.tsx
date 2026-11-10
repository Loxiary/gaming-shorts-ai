import { useCallback, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";

import { ProjectForm } from "./ProjectForm";
import { SourcePanel } from "./SourcePanel";
import { TranscriptPanel } from "./TranscriptPanel";
import { AnalysisPanel } from "../analysis/AnalysisPanel";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { EmptyState, ErrorBox, Loading } from "../../components/Feedback";
import { JobCard } from "../../components/JobCard";
import { ApiError, errorMessage } from "../../services/api";
import { formatBytes, formatDate } from "../../services/format";
import {
  useCreateJob,
  useDeleteProject,
  useJobKinds,
  useProject,
  useUpdateProject,
} from "../../services/queries";

export function ProjectDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const project = useProject(id);
  const kinds = useJobKinds();
  const update = useUpdateProject(id);
  const remove = useDeleteProject();
  const createJob = useCreateJob();
  const [editing, setEditing] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const stopAt = useRef<number | null>(null);

  // Lecture d'un extrait : saut au début, arrêt automatique à la fin.
  const previewRange = useCallback((start: number, end: number) => {
    const video = videoRef.current;
    if (!video) return;
    stopAt.current = end;
    video.currentTime = start;
    video.scrollIntoView({ behavior: "smooth", block: "center" });
    const onTime = () => {
      if (stopAt.current != null && video.currentTime >= stopAt.current) {
        video.pause();
        stopAt.current = null;
        video.removeEventListener("timeupdate", onTime);
      }
    };
    video.addEventListener("timeupdate", onTime);
    void video.play().catch(() => undefined);
  }, []);

  if (project.isPending) return <Loading />;
  if (project.isError) {
    if (project.error instanceof ApiError && project.error.status === 404) {
      return (
        <section>
          <h1>Projet introuvable</h1>
          <p>
            Ce projet n'existe pas ou a été supprimé.{" "}
            <Link to="/projets">Retour à la bibliothèque</Link>
          </p>
        </section>
      );
    }
    return <ErrorBox error={project.error} onRetry={() => project.refetch()} />;
  }

  const p = project.data;

  return (
    <section>
      <p>
        <Link to="/projets">← Bibliothèque</Link>
      </p>
      <div className="page-header">
        <h1>
          {p.name} {p.is_test && <span className="badge badge-demo">Test</span>}
        </h1>
        {!editing && (
          <div className="job-actions">
            <button type="button" className="btn" onClick={() => setEditing(true)}>
              Modifier
            </button>
            <button type="button" className="btn btn-danger" onClick={() => setConfirmDelete(true)}>
              Supprimer
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <div className="card">
          <ProjectForm
            initial={p}
            submitLabel="Enregistrer"
            pending={update.isPending}
            error={update.error}
            onCancel={() => {
              setEditing(false);
              update.reset();
            }}
            onSubmit={(data) =>
              update.mutate(
                { name: data.name, game: data.game, description: data.description },
                { onSuccess: () => setEditing(false) },
              )
            }
          />
        </div>
      ) : (
        <div className="card">
          <dl className="details">
            <div>
              <dt>Jeu</dt>
              <dd>{p.game ?? "—"}</dd>
            </div>
            <div>
              <dt>Description</dt>
              <dd>{p.description ?? "—"}</dd>
            </div>
            <div>
              <dt>Créé le</dt>
              <dd>{formatDate(p.created_at)}</dd>
            </div>
            <div>
              <dt>Modifié le</dt>
              <dd>{formatDate(p.updated_at)}</dd>
            </div>
            <div>
              <dt>Identifiant</dt>
              <dd>
                <code>{p.id}</code>
              </dd>
            </div>
          </dl>
        </div>
      )}

      {p.source && <SourcePanel key={p.source.id} projectId={p.id} source={p.source} />}

      {p.source && (
        <AnalysisPanel
          projectId={p.id}
          ready={Boolean(p.transcript && p.source.media_available)}
          jobs={p.jobs}
          onPreview={previewRange}
        />
      )}

      {p.transcript ? (
        <TranscriptPanel
          projectId={p.id}
          summary={p.transcript}
          mediaAvailable={p.source?.media_available ?? false}
          videoRef={videoRef}
        />
      ) : (
        p.source && (
          <div className="card">
            <h2>Transcription source</h2>
            <p className="muted">
              Pas encore de transcription : elle apparaîtra ici à la fin du job d'import.
            </p>
          </div>
        )
      )}

      <h2>Jobs du projet</h2>
      {p.jobs.length === 0 ? (
        <EmptyState>Aucun job pour ce projet.</EmptyState>
      ) : (
        <div className="job-list">
          {p.jobs.map((job) => (
            <JobCard key={job.id} job={job} showProject={false} />
          ))}
        </div>
      )}

      <details className="card tools" open={!p.source}>
        <summary>Outils de test : jobs de démonstration</summary>
        <p className="muted">
          Ces jobs simulent des étapes pour tester la file d'attente persistante. Ils ne
          téléchargent, n'analysent et ne génèrent aucune vidéo.
        </p>
        {kinds.isError && <ErrorBox error={kinds.error} />}
        <div className="kind-list">
          {kinds.data
            ?.filter((k) => k.is_demo)
            .map((k) => (
              <div key={k.kind} className="kind">
                <div>
                  <strong>{k.label}</strong>
                  <p className="muted">{k.description}</p>
                </div>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={createJob.isPending}
                  onClick={() => createJob.mutate({ projectId: p.id, kind: k.kind })}
                >
                  Ajouter à la file
                </button>
              </div>
            ))}
        </div>
        {createJob.isError && (
          <p className="job-error" role="alert">
            {errorMessage(createJob.error)}
          </p>
        )}
      </details>

      {confirmDelete && (
        <ConfirmDialog
          title="Supprimer ce projet ?"
          danger
          confirmLabel="Supprimer définitivement"
          pending={remove.isPending}
          message={
            <>
              <p>
                Le projet <strong>{p.name}</strong> et l'historique de ses {p.jobs.length} job(s)
                seront supprimés de la bibliothèque. Cette action est irréversible.
              </p>
              {p.files_size_bytes > 0 && (
                <p>
                  Les fichiers locaux du projet (vidéo source, audio extrait :{" "}
                  <strong>{formatBytes(p.files_size_bytes)}</strong>) seront aussi effacés du
                  disque.
                </p>
              )}
              {remove.isError && <p className="job-error">{errorMessage(remove.error)}</p>}
            </>
          }
          onCancel={() => {
            setConfirmDelete(false);
            remove.reset();
          }}
          onConfirm={() =>
            remove.mutate(p.id, { onSuccess: () => navigate("/projets", { replace: true }) })
          }
        />
      )}
    </section>
  );
}
