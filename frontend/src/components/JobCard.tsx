import { useState } from "react";
import { Link } from "react-router";

import { errorMessage } from "../services/api";
import { DemoBadge, JobStatusBadge, ProgressBar, StepStatusBadge } from "./StatusBadge";
import { formatBytes, formatDate, formatDuration } from "../services/format";
import { useCancelJob, useJob, usePauseJob, useResumeJob, useRetryJob } from "../services/queries";
import type { Job } from "../services/types";

interface Props {
  job: Job;
  showProject?: boolean;
}

export function JobCard({ job, showProject = true }: Props) {
  const [expanded, setExpanded] = useState(false);
  const detail = useJob(job.id, expanded);
  const cancel = useCancelJob();
  const retry = useRetryJob();
  const pause = usePauseJob();
  const resume = useResumeJob();

  const active = job.status === "queued" || job.status === "running" || job.status === "paused";
  const canCancel = active && !job.cancel_requested;
  const canRetry = job.status === "failed" || job.status === "cancelled";
  const canPause =
    (job.status === "queued" || job.status === "running") &&
    !job.pause_requested &&
    !job.cancel_requested;
  const canResume = job.status === "paused" || Boolean(job.pause_requested);
  const actionError = cancel.error ?? retry.error ?? pause.error ?? resume.error;

  return (
    <article className="job-card" aria-label={`Job ${job.kind_label}`}>
      <header className="job-card-header">
        <div className="job-title">
          <JobStatusBadge status={job.status} />
          <strong>{job.kind_label}</strong>
          {job.is_demo && <DemoBadge />}
        </div>
        <div className="job-actions">
          {canPause && (
            <button
              type="button"
              className="btn btn-small"
              onClick={() => pause.mutate(job.id)}
              disabled={pause.isPending}
              title="Pause entre deux étapes : l'étape en cours se termine d'abord"
            >
              Pause
            </button>
          )}
          {canResume && (
            <button
              type="button"
              className="btn btn-small btn-primary"
              onClick={() => resume.mutate(job.id)}
              disabled={resume.isPending}
            >
              Reprendre
            </button>
          )}
          {canCancel && (
            <button
              type="button"
              className="btn btn-small"
              onClick={() => cancel.mutate(job.id)}
              disabled={cancel.isPending}
            >
              Annuler
            </button>
          )}
          {canRetry && (
            <button
              type="button"
              className="btn btn-small btn-primary"
              onClick={() => retry.mutate(job.id)}
              disabled={retry.isPending}
            >
              Relancer
            </button>
          )}
          <button
            type="button"
            className="btn btn-small btn-ghost"
            aria-expanded={expanded}
            onClick={() => setExpanded((v) => !v)}
          >
            {expanded ? "Masquer les étapes" : "Voir les étapes"}
          </button>
        </div>
      </header>

      <ProgressBar value={job.progress} label={`Progression du job ${job.kind_label}`} />
      {job.status === "running" && job.current_step_label && (
        <p className="current-step">
          {job.current_step_label}
          {job.current_step_detail && <span className="muted"> — {job.current_step_detail}</span>}
        </p>
      )}

      <dl className="job-meta">
        {showProject && (
          <div>
            <dt>Projet</dt>
            <dd>
              <Link to={`/projets/${job.project_id}`}>{job.project_name}</Link>
            </dd>
          </div>
        )}
        <div>
          <dt>Créé</dt>
          <dd>{formatDate(job.created_at)}</dd>
        </div>
        <div>
          <dt>Durée</dt>
          <dd>{formatDuration(job.started_at, job.finished_at)}</dd>
        </div>
        <div>
          <dt>Tentatives</dt>
          <dd>{job.attempts}</dd>
        </div>
      </dl>

      {job.pause_requested && job.status === "running" && (
        <p className="note">
          Pause demandée : elle prendra effet à la fin de l'étape en cours. Les étapes terminées
          sont conservées.
        </p>
      )}
      {job.status === "paused" && (
        <p className="note">
          En pause : « Reprendre » remet le job dans la file, à l'étape où il s'est arrêté.
        </p>
      )}
      {job.cancel_requested && job.status === "running" && (
        <p className="note">
          Annulation demandée : elle prendra effet au prochain point d'arrêt sûr de l'étape en
          cours.
        </p>
      )}
      {job.error_message && <p className="job-error">{job.error_message}</p>}
      {actionError && <p className="job-error">{errorMessage(actionError)}</p>}

      {expanded && (
        <ol className="steps">
          {detail.isPending && <li className="muted">Chargement des étapes…</li>}
          {detail.isError && <li className="job-error">{errorMessage(detail.error)}</li>}
          {detail.data?.steps.map((step) => (
            <li key={step.position} className="step">
              <StepStatusBadge status={step.status} />
              <span>{step.label}</span>
              {step.status === "running" ? (
                <span className="muted">
                  {Math.round(step.progress * 100)} %{step.detail ? ` — ${step.detail}` : ""}
                </span>
              ) : (
                <span className="muted">{formatDuration(step.started_at, step.finished_at)}</span>
              )}
              {step.status === "completed" && <StepSummary output={step.output} />}
              {step.error_message && <span className="job-error">{step.error_message}</span>}
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}

function StepSummary({ output }: { output: Record<string, unknown> | null }) {
  if (!output) return null;
  const parts: string[] = [];
  if (typeof output.title === "string") parts.push(output.title);
  if (typeof output.size_bytes === "number") parts.push(formatBytes(output.size_bytes));
  if (output.reused === true) parts.push("fichier existant réutilisé");
  if (typeof output.width === "number" && typeof output.height === "number")
    parts.push(`${output.width}×${output.height}`);
  if (typeof output.segments === "number") parts.push(`${output.segments} segments`);
  if (typeof output.language === "string") parts.push(`langue ${output.language}`);
  if (typeof output.device === "string") parts.push(output.device === "cuda" ? "GPU" : "CPU");
  if (typeof output.realtime_factor === "number")
    parts.push(`${output.realtime_factor}× temps réel`);
  if (
    typeof output.vram_peak_used_mib === "number" &&
    typeof output.vram_baseline_used_mib === "number"
  )
    parts.push(`VRAM +${output.vram_peak_used_mib - output.vram_baseline_used_mib} Mio`);
  if (Array.isArray(output.warnings) && output.warnings.length > 0)
    parts.push(`⚠ ${output.warnings.join(" ; ")}`);
  return parts.length ? <span className="muted step-summary">{parts.join(" · ")}</span> : null;
}
