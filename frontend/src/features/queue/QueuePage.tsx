import { useState } from "react";

import { EmptyState, ErrorBox, Loading } from "../../components/Feedback";
import { JobCard } from "../../components/JobCard";
import { JOB_STATUS_LABELS } from "../../services/format";
import { useJobs } from "../../services/queries";
import type { JobStatus } from "../../services/types";

const FILTERS: (JobStatus | "all")[] = [
  "all",
  "queued",
  "running",
  "paused",
  "completed",
  "failed",
  "cancelled",
];

export function QueuePage() {
  const [filter, setFilter] = useState<JobStatus | "all">("all");
  const jobs = useJobs(filter === "all" ? {} : { status: filter });

  return (
    <section>
      <h1>File d'attente</h1>
      <p className="muted">
        Les jobs sont traités un par un par le worker, dans l'ordre d'arrivée. Leur état est
        enregistré en base : ils survivent à un redémarrage et reprennent à la dernière étape
        valide.
      </p>

      <div className="filters" role="group" aria-label="Filtrer par statut">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            className={filter === f ? "chip active" : "chip"}
            aria-pressed={filter === f}
            onClick={() => setFilter(f)}
          >
            {f === "all" ? "Tous" : JOB_STATUS_LABELS[f]}
          </button>
        ))}
      </div>

      {jobs.isPending && <Loading />}
      {jobs.isError && <ErrorBox error={jobs.error} onRetry={() => jobs.refetch()} />}
      {jobs.data && jobs.data.length === 0 && <EmptyState>Aucun job pour ce filtre.</EmptyState>}
      {jobs.data && jobs.data.length > 0 && (
        <div className="job-list">
          {jobs.data.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </section>
  );
}
