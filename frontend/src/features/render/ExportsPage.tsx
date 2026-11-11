import { Link } from "react-router";

import { EmptyState, ErrorBox, Loading } from "../../components/Feedback";
import { formatDate, formatTimecode } from "../../services/format";
import { useExports } from "../../services/renderApi";

export function ExportsPage() {
  const exports = useExports();
  if (exports.isPending) return <Loading />;
  if (exports.isError) return <ErrorBox error={exports.error} onRetry={() => exports.refetch()} />;

  return (
    <section>
      <h1>Exports</h1>
      <p className="muted">
        Shorts exportés après confirmation. Chaque fichier MP4 est accompagné d'une fiche JSON
        (source, droits déclarés, contrôle qualité, rapport de risques, avertissements acceptés).
        Aucune publication n'est faite par l'application.
      </p>
      {exports.data.length === 0 ? (
        <EmptyState>Aucun short exporté pour le moment.</EmptyState>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Exporté le</th>
                <th>Extrait</th>
                <th>Profil</th>
                <th>Fichier</th>
              </tr>
            </thead>
            <tbody>
              {exports.data.map((r) => (
                <tr key={r.id}>
                  <td>{formatDate(r.export_confirmed_at)}</td>
                  <td>
                    <Link to={`/projets/${r.project_id}`}>
                      {formatTimecode(r.start_seconds)} → {formatTimecode(r.end_seconds)}
                    </Link>
                  </td>
                  <td>{r.profile_name}</td>
                  <td>
                    <code>{r.exported_path}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
