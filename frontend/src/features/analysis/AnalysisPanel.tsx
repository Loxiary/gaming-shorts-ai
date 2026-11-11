import { useState } from "react";
import { Link } from "react-router";

import { CandidateCard } from "./CandidateCard";
import { ErrorBox, Loading } from "../../components/Feedback";
import {
  formatUsd,
  useAnalyses,
  useAnalysis,
  useAnalysisEstimate,
  useCreateAnalysis,
  useProfiles,
  useReselect,
} from "../../services/analysisApi";
import type { Analysis, AnalysisEngine } from "../../services/analysisTypes";
import { errorMessage } from "../../services/api";
import { formatDate } from "../../services/format";
import { useCreateRender } from "../../services/renderApi";
import type { Job } from "../../services/types";

const ENGINE_LABELS: Record<string, string> = {
  llm: "IA",
  signals: "signaux seuls (sans IA)",
  mixed: "IA puis signaux (plafond atteint)",
  auto: "automatique",
};

interface Props {
  projectId: string;
  ready: boolean;
  jobs: Job[];
  onPreview: (start: number, end: number) => void;
}

export function AnalysisPanel({ projectId, ready, jobs, onPreview }: Props) {
  const profiles = useProfiles();
  const [profileId, setProfileId] = useState<string>("");
  const [engine, setEngine] = useState<AnalysisEngine>("auto");
  const estimate = useAnalysisEstimate(projectId, profileId || undefined);
  const create = useCreateAnalysis(projectId);
  const analyses = useAnalyses(projectId);

  const latest = analyses.data?.[0];
  const running = jobs.some(
    (j) => j.kind === "analyze_clips" && (j.status === "queued" || j.status === "running"),
  );
  const est = estimate.data;
  const aiPossible = Boolean(est?.key_configured && est?.api_enabled);

  return (
    <div className="card">
      <h2>Détection des clips</h2>
      {!ready ? (
        <p className="muted">
          Disponible une fois l'import terminé (vidéo téléchargée et transcrite).
        </p>
      ) : (
        <>
          <div className="analyze-form">
            <label>
              Profil de montage
              <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                <option value="">
                  Profil par défaut
                  {profiles.data?.find((p) => p.is_default)
                    ? ` (${profiles.data.find((p) => p.is_default)?.name})`
                    : ""}
                </option>
                {profiles.data
                  ?.filter((p) => !p.is_default)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </label>
            <label>
              Évaluation
              <select value={engine} onChange={(e) => setEngine(e.target.value as AnalysisEngine)}>
                <option value="auto">Automatique (IA si disponible)</option>
                <option value="llm" disabled={!aiPossible}>
                  IA uniquement
                </option>
                <option value="signals">Signaux seuls (gratuit, approximatif)</option>
              </select>
            </label>
            <button
              type="button"
              className="btn btn-primary"
              disabled={create.isPending || running}
              onClick={() => create.mutate({ profileId: profileId || null, engine })}
            >
              {running ? "Analyse en cours…" : "Lancer l'analyse"}
            </button>
          </div>
          {est && (
            <p className="hint">
              {est.expected_candidates} extrait(s) environ.{" "}
              {engine === "signals" ? (
                "Aucun coût (analyse locale)."
              ) : aiPossible ? (
                <>
                  Coût IA estimé : <strong>≈ {formatUsd(est.estimated_cost_usd)}</strong> (
                  {est.model}) — dépensé ce mois-ci : {formatUsd(est.month_spent_usd)} sur{" "}
                  {formatUsd(est.monthly_cap_usd)}. Le plafond est vérifié avant chaque appel.
                </>
              ) : (
                <>
                  IA indisponible ({est.key_configured ? "API désactivée" : "clé API absente"}) :
                  l'évaluation se fera par signaux, sans IA. Voir{" "}
                  <Link to="/parametres">Paramètres</Link>.
                </>
              )}
            </p>
          )}
          {create.isError && (
            <p className="job-error" role="alert">
              {errorMessage(create.error)}
            </p>
          )}
        </>
      )}

      {analyses.isError && <ErrorBox error={analyses.error} />}
      {latest && (
        <AnalysisResults
          key={latest.id}
          summary={latest}
          running={running}
          onPreview={onPreview}
          olderCount={(analyses.data?.length ?? 1) - 1}
        />
      )}
    </div>
  );
}

function AnalysisResults({
  summary,
  running,
  onPreview,
  olderCount,
}: {
  summary: Analysis;
  running: boolean;
  onPreview: (start: number, end: number) => void;
  olderCount: number;
}) {
  const analysis = useAnalysis(summary.id, running);
  const reselect = useReselect(summary.id);
  const createRender = useCreateRender();
  const [draft, setDraft] = useState<number | null>(null);

  if (analysis.isPending) return <Loading label="Chargement des extraits…" />;
  if (analysis.isError) return <ErrorBox error={analysis.error} />;
  const a = analysis.data;
  const threshold = draft ?? a.threshold;
  const ranked = [...a.candidates].sort(
    (x, y) => (y.overall_score ?? -1) - (x.overall_score ?? -1),
  );

  return (
    <div className="analysis-results">
      <h3>
        Analyse du {formatDate(a.created_at)} — profil « {a.profile_name} »
        {olderCount > 0 && (
          <span className="muted"> ({olderCount} analyse(s) plus ancienne(s))</span>
        )}
      </h3>
      <p className="muted">
        Évaluation : {ENGINE_LABELS[a.engine ?? "auto"] ?? a.engine}
        {a.llm_model ? ` (${a.llm_model})` : ""} · coût {formatUsd(a.cost_usd)} ·{" "}
        {a.candidate_count} extrait(s), {a.selected_count} sélectionné(s). Les notes sont des
        estimations éditoriales, pas des prédictions de vues.
      </p>
      {a.notes.map((n) => (
        <div key={n} className="alert alert-warn" role="note">
          {n}
        </div>
      ))}

      {a.candidates.length > 0 && (
        <div className="threshold">
          <label>
            Seuil de sélection : <strong>{threshold}</strong>/100
            <input
              type="range"
              min={0}
              max={100}
              step={1}
              value={threshold}
              onChange={(e) => setDraft(Number(e.target.value))}
            />
          </label>
          <button
            type="button"
            className="btn btn-small"
            disabled={reselect.isPending || threshold === a.threshold}
            onClick={() => reselect.mutate(threshold, { onSuccess: () => setDraft(null) })}
          >
            Appliquer le seuil
          </button>
          <span className="hint">Recalcule la sélection sans nouvel appel à l'IA.</span>
          {reselect.isError && <span className="job-error">{errorMessage(reselect.error)}</span>}
        </div>
      )}

      {!running && a.candidates.length > 0 && a.selected_count === 0 && (
        <div className="alert alert-warn" role="note">
          Aucun extrait n'atteint le seuil de {a.threshold} (meilleure note :{" "}
          {Math.round(Math.max(...a.candidates.map((c) => c.overall_score ?? 0)))}). La vidéo ne
          contient peut-être pas de moment adapté à ce profil : essayez un autre profil ou abaissez
          le seuil.
        </div>
      )}
      {running && a.candidates.length === 0 && <Loading label="Analyse en cours…" />}
      {createRender.isError && (
        <p className="job-error" role="alert">
          {errorMessage(createRender.error)}
        </p>
      )}
      {createRender.isSuccess && (
        <p className="note" role="status">
          Montage ajouté à la file : suivez-le dans « Shorts montés » plus bas.
        </p>
      )}
      <div className="candidate-list">
        {ranked.map((c, i) => (
          <CandidateCard
            key={c.id}
            candidate={c}
            rank={i + 1}
            onPreview={onPreview}
            onRender={(id) => createRender.mutate(id)}
            renderPending={createRender.isPending}
          />
        ))}
      </div>
    </div>
  );
}
