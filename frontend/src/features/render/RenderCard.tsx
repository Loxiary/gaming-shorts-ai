import { useState } from "react";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ProgressBar } from "../../components/StatusBadge";
import { formatUsd } from "../../services/analysisApi";
import { errorMessage } from "../../services/api";
import { formatBytes, formatDate, formatTimecode } from "../../services/format";
import { useJob } from "../../services/queries";
import {
  type Render,
  type RiskReport,
  useConfirmExport,
  useDeleteRender,
} from "../../services/renderApi";

const LEVEL_CLASS: Record<string, string> = {
  faible: "badge-completed",
  modéré: "badge-cancelled",
  modérée: "badge-cancelled",
  élevé: "badge-failed",
};

export function RenderCard({ render: r }: { render: Render }) {
  const running = r.job_status === "queued" || r.job_status === "running";
  const job = useJob(r.job_id ?? "", running && Boolean(r.job_id));
  const exportMutation = useConfirmExport();
  const remove = useDeleteRender();
  const [confirming, setConfirming] = useState(false);
  const [acknowledged, setAcknowledged] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [tab, setTab] = useState<"plan" | "qc" | "risk">("risk");
  const currentStep = job.data?.steps.find((s) => s.status === "running");

  return (
    <article className="render" aria-label={`Short ${formatTimecode(r.start_seconds)}`}>
      <div className="render-media">
        {r.video_url ? (
          <video className="vertical" src={r.video_url} controls preload="metadata" />
        ) : (
          <div className="vertical placeholder">
            {running ? "Montage en cours…" : r.job_status === "failed" ? "Échec" : "—"}
          </div>
        )}
      </div>
      <div className="render-body">
        <header className="page-header">
          <h3>
            Short {formatTimecode(r.start_seconds)} → {formatTimecode(r.end_seconds)}{" "}
            <span className="muted">({Math.round(r.duration_seconds)} s)</span>
          </h3>
          <div className="candidate-badges">
            {r.export_status === "exported" ? (
              <span className="badge badge-completed">Exporté</span>
            ) : r.ready ? (
              <span className="badge badge-running">Prêt à exporter</span>
            ) : running ? (
              <span className="badge badge-queued">Montage en cours</span>
            ) : (
              <span className="badge badge-failed">Non exportable</span>
            )}
            {r.subtitles_are_translation && (
              <span className="badge badge-demo">
                Sous-titres traduits ({r.subtitle_language}) — traduction, pas verbatim
              </span>
            )}
          </div>
        </header>
        <p className="hint">
          Profil « {r.profile_name} » · plan {r.plan_engine === "llm" ? "par IA" : "sans IA"} · coût{" "}
          {formatUsd(r.cost_usd)}
          {r.output_size_bytes ? ` · ${formatBytes(r.output_size_bytes)}` : ""} · créé le{" "}
          {formatDate(r.created_at)}
        </p>

        {running && job.data && (
          <>
            <ProgressBar value={job.data.progress} label="Progression du montage" />
            {currentStep && (
              <p className="current-step">
                {currentStep.label}
                {currentStep.detail && <span className="muted"> — {currentStep.detail}</span>}
              </p>
            )}
          </>
        )}
        {r.job_error && <p className="job-error">{r.job_error}</p>}

        {(r.plan || r.qc || r.risk_report) && (
          <div className="filters" role="tablist" aria-label="Détails du short">
            {(
              [
                ["risk", "Rapport de risques"],
                ["qc", "Contrôle qualité"],
                ["plan", "Plan éditorial"],
              ] as const
            ).map(([key, label]) => (
              <button
                key={key}
                type="button"
                role="tab"
                aria-selected={tab === key}
                className={tab === key ? "chip active" : "chip"}
                onClick={() => setTab(key)}
              >
                {label}
              </button>
            ))}
          </div>
        )}

        {tab === "plan" && r.plan && (
          <dl className="details">
            <div>
              <dt>Accroche</dt>
              <dd>
                {r.plan.hook_text || "—"}{" "}
                {r.plan.hook_text && (
                  <span className="badge badge-demo">
                    {r.plan.hook_kind === "quote" ? "citation réelle" : "texte original"}
                  </span>
                )}
              </dd>
            </div>
            <div>
              <dt>Appel à l'action</dt>
              <dd>{r.plan.cta_text || "—"}</dd>
            </div>
            <div>
              <dt>Mots en couleur</dt>
              <dd>{r.plan.keywords.join(", ") || "—"}</dd>
            </div>
            <div>
              <dt>Zooms</dt>
              <dd>
                {r.plan.zooms.length
                  ? r.plan.zooms.map((z) => `${formatTimecode(z.t)} (${z.reason})`).join(" · ")
                  : "aucun"}
              </dd>
            </div>
            {r.plan.warnings.length > 0 && (
              <div>
                <dt>Remarques</dt>
                <dd>
                  <ul className="warnings">
                    {r.plan.warnings.map((w) => (
                      <li key={w}>⚠ {w}</li>
                    ))}
                  </ul>
                </dd>
              </div>
            )}
          </dl>
        )}

        {tab === "qc" && r.qc && (
          <ul className="qc">
            {r.qc.checks.map((c) => (
              <li key={c.key} className={c.ok ? "ok" : c.level}>
                <span aria-hidden="true">{c.ok ? "✓" : c.level === "critical" ? "✗" : "⚠"}</span>{" "}
                {c.label} <span className="muted">— {c.detail}</span>
              </li>
            ))}
          </ul>
        )}

        {tab === "risk" && r.risk_report && <RiskReportView report={r.risk_report} />}

        <div className="job-actions render-actions">
          {r.export_status === "exported" ? (
            <p className="note">
              Exporté le {formatDate(r.export_confirmed_at)} : <code>{r.exported_path}</code>
            </p>
          ) : (
            <button
              type="button"
              className="btn btn-primary"
              disabled={!r.ready}
              title={r.ready ? undefined : "Le montage doit être terminé et le fichier valide"}
              onClick={() => {
                setAcknowledged(false);
                setConfirming(true);
              }}
            >
              Exporter…
            </button>
          )}
          {!running && (
            <button
              type="button"
              className="btn btn-small btn-danger"
              onClick={() => setDeleting(true)}
            >
              Supprimer le rendu
            </button>
          )}
        </div>
      </div>

      {confirming && (
        <ConfirmDialog
          title="Confirmer l'export de ce short ?"
          confirmLabel="Exporter malgré les avertissements"
          pending={exportMutation.isPending}
          confirmDisabled={!acknowledged}
          onCancel={() => {
            setConfirming(false);
            exportMutation.reset();
          }}
          onConfirm={() => {
            if (!acknowledged) return;
            exportMutation.mutate(r.id, { onSuccess: () => setConfirming(false) });
          }}
          message={
            <>
              <p>Avant d'exporter, lisez ces avertissements :</p>
              <ul className="warnings">
                {r.export_warnings.map((w) => (
                  <li key={w}>⚠ {w}</li>
                ))}
              </ul>
              <p className="hint">
                Ces avertissements sont informatifs : la décision vous appartient. Le fichier sera
                copié dans le dossier d'exports avec une fiche de métadonnées.
              </p>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={acknowledged}
                  onChange={(e) => setAcknowledged(e.target.checked)}
                />{" "}
                J'ai lu ces avertissements et je confirme l'export.
              </label>
              {exportMutation.isError && (
                <p className="job-error">{errorMessage(exportMutation.error)}</p>
              )}
            </>
          }
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="Supprimer ce rendu ?"
          danger
          confirmLabel="Supprimer"
          pending={remove.isPending}
          onCancel={() => setDeleting(false)}
          onConfirm={() => remove.mutate(r.id, { onSuccess: () => setDeleting(false) })}
          message={
            <p>
              Le fichier de travail du rendu sera effacé.
              {r.export_status === "exported" && " Le fichier exporté est conservé."}
            </p>
          }
        />
      )}
    </article>
  );
}

function RiskReportView({ report }: { report: RiskReport }) {
  return (
    <div className="risk">
      <p className="hint">{report.disclaimer}</p>
      <dl className="details">
        <div>
          <dt>Source</dt>
          <dd>
            {report.source.title ?? "?"} — {report.source.creator ?? "créateur inconnu"} · licence :{" "}
            {report.source.platform_license}
          </dd>
        </div>
        <div>
          <dt>Droits</dt>
          <dd>
            {report.rights.label}
            {report.rights.note && <span className="muted"> ({report.rights.note})</span>}
          </dd>
        </div>
        <div>
          <dt>Contenu réutilisé</dt>
          <dd>
            <span className={`badge ${LEVEL_CLASS[report.reused_content.level] ?? ""}`}>
              Risque {report.reused_content.level}
            </span>{" "}
            {report.reused_content.detail}
          </dd>
        </div>
        <div>
          <dt>Transformation éditoriale</dt>
          <dd>
            <span className={`badge ${LEVEL_CLASS[report.transformation.level] ?? ""}`}>
              {report.transformation.level}
            </span>{" "}
            Ajouts : {report.transformation.added.join(", ")}. Manque :{" "}
            {report.transformation.missing.join(", ")}.
          </dd>
        </div>
        <div>
          <dt>Musique / audio</dt>
          <dd>{report.audio_music.detail}</dd>
        </div>
        <div>
          <dt>Facecam</dt>
          <dd>{report.facecam.detail}</dd>
        </div>
        {report.ai_warnings.length > 0 && (
          <div>
            <dt>Avertissements de l'analyse</dt>
            <dd>
              <ul className="warnings">
                {report.ai_warnings.map((w) => (
                  <li key={w}>⚠ {w}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
        <div>
          <dt>Recommandations</dt>
          <dd>
            <ul className="plain">
              {report.recommendations.map((w) => (
                <li key={w}>→ {w}</li>
              ))}
            </ul>
          </dd>
        </div>
      </dl>
    </div>
  );
}
