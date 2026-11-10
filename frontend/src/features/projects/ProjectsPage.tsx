import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { ProjectForm } from "./ProjectForm";
import { EmptyState, ErrorBox, Loading } from "../../components/Feedback";
import { formatDate } from "../../services/format";
import { useCreateProject, useProjects } from "../../services/queries";

export function ProjectsPage() {
  const projects = useProjects();
  const create = useCreateProject();
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);

  return (
    <section>
      <div className="page-header">
        <h1>Bibliothèque de projets</h1>
        {!showForm && (
          <button type="button" className="btn btn-primary" onClick={() => setShowForm(true)}>
            Nouveau projet
          </button>
        )}
      </div>

      {showForm && (
        <div className="card">
          <h2>Nouveau projet</h2>
          <p className="muted">
            Un projet regroupe une source et ses traitements. En Phase 1, il ne contient pas encore
            de vidéo : seuls des jobs de démonstration peuvent y être lancés.
          </p>
          <ProjectForm
            submitLabel="Créer le projet"
            pending={create.isPending}
            error={create.error}
            showTestFlag
            onCancel={() => {
              setShowForm(false);
              create.reset();
            }}
            onSubmit={(data) =>
              create.mutate(data, {
                onSuccess: (project) => navigate(`/projets/${project.id}`),
              })
            }
          />
        </div>
      )}

      {projects.isPending && <Loading />}
      {projects.isError && <ErrorBox error={projects.error} onRetry={() => projects.refetch()} />}
      {projects.data && projects.data.length === 0 && (
        <EmptyState>
          Aucun projet pour le moment. Créez un projet de test pour commencer.
        </EmptyState>
      )}
      {projects.data && projects.data.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Nom</th>
                <th>Jeu</th>
                <th>Jobs</th>
                <th>Créé le</th>
              </tr>
            </thead>
            <tbody>
              {projects.data.map((p) => (
                <tr key={p.id}>
                  <td>
                    <Link to={`/projets/${p.id}`}>{p.name}</Link>
                    {p.is_test && <span className="badge badge-demo">Test</span>}
                  </td>
                  <td>{p.game ?? "—"}</td>
                  <td>
                    {p.job_counts.total}
                    {p.job_counts.running + p.job_counts.queued > 0 && (
                      <span className="muted">
                        {" "}
                        ({p.job_counts.running + p.job_counts.queued} actif(s))
                      </span>
                    )}
                  </td>
                  <td>{formatDate(p.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
