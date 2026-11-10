import { useState } from "react";
import { Link } from "react-router";

import { errorMessage } from "../services/api";
import { DemoBadge, JobStatusBadge, ProgressBar, StepStatusBadge } from "./StatusBadge";
import { formatDate, formatDuration } from "../services/format";
import { useCancelJob, useJob, useRetryJob } from "../services/queries";
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

  const canCancel = (job.status === "queued" || job.status === "running") && !job.cancel_requested;
  const canRetry = job.status === "failed" || job.status === "cancelled";
  const actionError = cancel.error ?? retry.error;

  return (
    <article className="job-card" aria-label={`Job ${job.kind_label}`}>
      <header className="job-card-header">
        <div className="job-title">
          <JobStatusBadge status={job.status} />
          <strong>{job.kind_label}</strong>
          {job.is_demo && <DemoBadge />}
        </div>
        <div className="job-actions">
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

      {job.cancel_requested && job.status === "running" && (
        <p className="note">
          Annulation demandée : elle prendra effet à la fin de l'étape en cours.
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
              <span className="muted">{formatDuration(step.started_at, step.finished_at)}</span>
              {step.error_message && <span className="job-error">{step.error_message}</span>}
            </li>
          ))}
        </ol>
      )}
    </article>
  );
}
