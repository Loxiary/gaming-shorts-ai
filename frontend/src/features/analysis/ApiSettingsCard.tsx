import { useState } from "react";

import { ErrorBox, Loading } from "../../components/Feedback";
import { formatUsd, useApiSettings, useUpdateApiSettings } from "../../services/analysisApi";
import { errorMessage } from "../../services/api";

export function ApiSettingsCard() {
  const settings = useApiSettings();
  const update = useUpdateApiSettings();
  const [cap, setCap] = useState<string | null>(null);

  if (settings.isPending) return <Loading />;
  if (settings.isError) return <ErrorBox error={settings.error} />;
  const s = settings.data;
  const capValue = cap ?? String(s.monthly_cap_usd);

  return (
    <div className="card">
      <h2>IA d'évaluation des clips</h2>
      <dl className="details">
        <div>
          <dt>Fournisseur / modèle</dt>
          <dd>
            Anthropic · {s.model} (effort {s.effort})
          </dd>
        </div>
        <div>
          <dt>Clé API</dt>
          <dd>
            {s.key_configured ? (
              <span className="badge badge-completed">Configurée</span>
            ) : (
              <>
                <span className="badge badge-failed">Absente</span>{" "}
                <span className="muted">
                  Ajoutez <code>ANTHROPIC_API_KEY=…</code> dans le fichier <code>.env</code> puis
                  redémarrez l'application. Sans clé, l'analyse fonctionne en mode « signaux seuls
                  ».
                </span>
              </>
            )}
          </dd>
        </div>
        <div>
          <dt>Tarifs utilisés</dt>
          <dd>
            {s.prices_per_mtok.input} $ / {s.prices_per_mtok.output} $ par million de jetons (entrée
            / sortie)
          </dd>
        </div>
        <div>
          <dt>Dépensé ce mois-ci</dt>
          <dd>
            {formatUsd(s.month_spent_usd)} sur {formatUsd(s.monthly_cap_usd)}
          </dd>
        </div>
      </dl>
      <div className="api-controls">
        <label className="checkbox">
          <input
            type="checkbox"
            checked={s.api_enabled}
            disabled={update.isPending}
            onChange={(e) => update.mutate({ api_enabled: e.target.checked })}
          />
          Autoriser les appels payants à l'API
        </label>
        <label>
          Plafond mensuel ($)
          <input
            type="number"
            min={0}
            step={1}
            value={capValue}
            onChange={(e) => setCap(e.target.value)}
          />
        </label>
        <button
          type="button"
          className="btn btn-small"
          disabled={update.isPending || cap === null || Number(cap) === s.monthly_cap_usd}
          onClick={() =>
            update.mutate({ monthly_cap_usd: Number(capValue) }, { onSuccess: () => setCap(null) })
          }
        >
          Enregistrer le plafond
        </button>
      </div>
      {update.isError && <p className="job-error">{errorMessage(update.error)}</p>}
    </div>
  );
}
