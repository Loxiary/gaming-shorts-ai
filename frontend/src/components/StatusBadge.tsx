import { JOB_STATUS_LABELS, STEP_STATUS_LABELS } from "../services/format";
import type { JobStatus, StepStatus } from "../services/types";

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return <span className={`badge badge-${status}`}>{JOB_STATUS_LABELS[status]}</span>;
}

export function StepStatusBadge({ status }: { status: StepStatus }) {
  return <span className={`badge badge-${status}`}>{STEP_STATUS_LABELS[status]}</span>;
}

export function DemoBadge() {
  return (
    <span className="badge badge-demo" title="Job de démonstration : aucun traitement réel">
      Démo
    </span>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const percent = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div
      className="progress"
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
    >
      <div className="progress-fill" style={{ width: `${percent}%` }} />
      <span className="progress-text">{percent} %</span>
    </div>
  );
}
