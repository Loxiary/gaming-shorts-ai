import { Link } from "react-router";

import { EmptyState, ErrorBox, Loading } from "../../components/Feedback";
import { JobCard } from "../../components/JobCard";
import { useHealth, useJobs, useProjects } from "../../services/queries";
import type { JobStatus } from "../../services/types";

const STAT_ORDER: { status: JobStatus; label: string }[] = [
  { status: "queued", label: "En attente" },
  { status: "running", label: "En cours" },
  { status: "completed", label: "Terminés" },
  { status: "failed", label: "En échec" },
];

export function DashboardPage() {
  const projects = useProjects();
  const jobs = useJobs();
  const health = useHealth();

  if (projects.isError)
    return <ErrorBox error={projects.error} onRetry={() => projects.refetch()} />;
  if (jobs.isError) return <ErrorBox error={jobs.error} onRetry={() => jobs.refetch()} />;
  if (projects.isPending || jobs.isPending) return <Loading />;

  const counts = Object.fromEntries(
    STAT_ORDER.map(({ status }) => [status, jobs.data.filter((j) => j.status === status).length]),
  ) as Record<JobStatus, number>;
  const active = jobs.data.filter((j) => j.status === "running" || j.status === "queued");

  return (
    <section>
      <h1>Tableau de bord</h1>

      <div className="stats">
        <div className="stat">
          <span className="stat-value">{projects.data.length}</span>
          <span className="stat-label">Projets</span>
        </div>
        {STAT_ORDER.map(({ status, label }) => (
          <div className={`stat stat-${status}`} key={status}>
            <span className="stat-value">{counts[status]}</span>
            <span className="stat-label">Jobs {label.toLowerCase()}</span>
          </div>
        ))}
      </div>

      {health.data && !health.data.worker.alive && active.length > 0 && (
        <div className="alert alert-warn" role="alert">
          Le worker est arrêté : {active.length} job(s) attendent. Lancez-le avec{" "}
          <code>scripts\start.ps1</code>.
        </div>
      )}

      <h2>Jobs actifs</h2>
      {active.length === 0 ? (
        <EmptyState>
          Aucun job en attente ou en cours. Créez un projet dans la{" "}
          <Link to="/projets">bibliothèque</Link> puis lancez un job de démonstration.
        </EmptyState>
      ) : (
        <div className="job-list">
          {active.map((job) => (
            <JobCard key={job.id} job={job} />
          ))}
        </div>
      )}
    </section>
  );
}
