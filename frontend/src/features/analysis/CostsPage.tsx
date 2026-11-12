import { Link } from "react-router";

import { ErrorBox, Loading } from "../../components/Feedback";
import { formatUsd, useCosts } from "../../services/analysisApi";
import { formatDate } from "../../services/format";

const STATUS_LABELS: Record<string, string> = {
  ok: "OK",
  refused: "Refus",
  failed: "Réponse invalide",
};

export function CostsPage() {
  const costs = useCosts();

  if (costs.isPending) return <Loading />;
  if (costs.isError) return <ErrorBox error={costs.error} onRetry={() => costs.refetch()} />;
  const c = costs.data;
  const ratio = c.monthly_cap_usd > 0 ? Math.min(c.month_spent_usd / c.monthly_cap_usd, 1) : 1;

  return (
    <section>
      <h1>Coûts API</h1>
      <p className="muted">
        Chaque appel à l'IA est enregistré avec ses jetons et son coût, calculé à partir des tarifs
        configurés : c'est une estimation proche de la facture, pas la facture elle-même. Le plafond
        se règle dans les <Link to="/parametres">Paramètres</Link>.
      </p>

      <div className="stats">
        <div className="stat">
          <span className="stat-value">{formatUsd(c.month_spent_usd)}</span>
          <span className="stat-label">Ce mois-ci ({c.calls_this_month} appels)</span>
        </div>
        <div className="stat">
          <span className="stat-value">{formatUsd(c.monthly_cap_usd)}</span>
          <span className="stat-label">Plafond mensuel</span>
        </div>
        <div className="stat">
          <span className="stat-value">{formatUsd(c.total_spent_usd)}</span>
          <span className="stat-label">Total depuis le début</span>
        </div>
      </div>
      <div
        className="progress"
        role="progressbar"
        aria-label="Part du plafond mensuel utilisée"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(ratio * 100)}
      >
        <div className="progress-fill" style={{ width: `${ratio * 100}%` }} />
        <span className="progress-text">{Math.round(ratio * 100)} % du plafond</span>
      </div>

      <h2>Par mois</h2>
      {c.by_month.length === 0 ? (
        <p className="muted">Aucun appel payant pour l'instant.</p>
      ) : (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Mois</th>
                <th>Appels</th>
                <th>Coût</th>
              </tr>
            </thead>
            <tbody>
              {c.by_month.map((m) => (
                <tr key={m.month}>
                  <td>{m.month}</td>
                  <td>{m.calls}</td>
                  <td>{formatUsd(m.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {c.recent.length > 0 && (
        <>
          <h2>Derniers appels</h2>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Modèle</th>
                  <th>Jetons entrée / sortie</th>
                  <th>Images</th>
                  <th>Statut</th>
                  <th>Coût</th>
                </tr>
              </thead>
              <tbody>
                {c.recent.map((u) => (
                  <tr key={u.id}>
                    <td>{formatDate(u.created_at)}</td>
                    <td>{u.model}</td>
                    <td>
                      {u.input_tokens.toLocaleString("fr-FR")}
                      {u.cache_read_tokens > 0 &&
                        ` (+${u.cache_read_tokens.toLocaleString("fr-FR")} en cache)`}{" "}
                      / {u.output_tokens.toLocaleString("fr-FR")}
                    </td>
                    <td>{u.images}</td>
                    <td title={u.detail ?? undefined}>{STATUS_LABELS[u.status] ?? u.status}</td>
                    <td>{formatUsd(u.cost_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
