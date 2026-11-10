import { useState } from "react";

import type { Candidate } from "../../services/analysisTypes";
import { formatTimecode } from "../../services/format";

const STATUS: Record<Candidate["status"], { label: string; cls: string }> = {
  scored: { label: "Évalué par IA", cls: "badge-running" },
  signals_only: { label: "Estimation sans IA", cls: "badge-cancelled" },
  failed: { label: "Échec de l'évaluation", cls: "badge-failed" },
  refused: { label: "Refusé par l'IA", cls: "badge-failed" },
  pending: { label: "En attente", cls: "badge-queued" },
};

interface Props {
  candidate: Candidate;
  rank: number;
  onPreview?: (start: number, end: number) => void;
}

export function CandidateCard({ candidate: c, rank, onPreview }: Props) {
  const [open, setOpen] = useState(false);
  const status = STATUS[c.status];

  return (
    <article
      className={c.selected ? "candidate selected" : "candidate"}
      aria-label={`Extrait ${formatTimecode(c.start_seconds)} – ${formatTimecode(c.end_seconds)}`}
    >
      <header className="candidate-header">
        <div className="candidate-score" title="Note globale pondérée selon le profil (0–100)">
          {c.overall_score != null ? Math.round(c.overall_score) : "—"}
        </div>
        <div className="candidate-title">
          <div>
            <strong>
              #{rank} · {formatTimecode(c.start_seconds)} → {formatTimecode(c.end_seconds)}
            </strong>{" "}
            <span className="muted">({Math.round(c.duration_seconds)} s)</span>
          </div>
          <div className="candidate-badges">
            {c.selected ? (
              <span className="badge badge-completed">Sélectionné</span>
            ) : (
              <span className="badge badge-queued">{c.rejection_reason ?? "Non sélectionné"}</span>
            )}
            <span className={`badge ${status.cls}`}>{status.label}</span>
            {c.confidence != null && (
              <span className="badge badge-demo" title="Confiance de l'évaluation">
                Confiance {Math.round(c.confidence * 100)} %
              </span>
            )}
          </div>
        </div>
        <div className="job-actions">
          {onPreview && (
            <button
              type="button"
              className="btn btn-small btn-primary"
              onClick={() => onPreview(c.start_seconds, c.end_seconds)}
            >
              Prévisualiser
            </button>
          )}
          <button
            type="button"
            className="btn btn-small btn-ghost"
            aria-expanded={open}
            onClick={() => setOpen((v) => !v)}
          >
            {open ? "Moins de détails" : "Détails"}
          </button>
        </div>
      </header>

      {c.summary && <p className="candidate-summary">{c.summary}</p>}
      {c.reason && (
        <p className="muted">
          <strong>Pourquoi :</strong> {c.reason}
        </p>
      )}
      {c.error_message && <p className="job-error">{c.error_message}</p>}
      {c.warnings.length > 0 && (
        <ul className="warnings">
          {c.warnings.map((w) => (
            <li key={w}>⚠ {w}</li>
          ))}
        </ul>
      )}

      {c.frames.length > 0 && (
        <div className="frames" aria-label="Images de l'extrait">
          {c.frames.map((f) => (
            <button
              key={f.url}
              type="button"
              className="frame"
              title={`Lire à ${formatTimecode(f.t)}`}
              onClick={() => onPreview?.(f.t, c.end_seconds)}
            >
              <img src={f.url} alt={`Image à ${formatTimecode(f.t)}`} loading="lazy" />
              <span>{formatTimecode(f.t)}</span>
            </button>
          ))}
        </div>
      )}

      {open && (
        <div className="candidate-details">
          <h3>Notes par critère</h3>
          <ul className="criteria">
            {c.scores.map((s) => (
              <li key={s.criterion}>
                <span className="criterion-label">{s.label}</span>
                <span className="meter" aria-label={`${s.label} : ${s.score} sur 10`}>
                  <span style={{ width: `${s.score * 10}%` }} />
                </span>
                <span className="criterion-score">{s.score}/10</span>
                {s.justification && <span className="muted criterion-why">{s.justification}</span>}
              </li>
            ))}
          </ul>
          {c.events.length > 0 && (
            <>
              <h3>Moments notables</h3>
              <ul className="plain">
                {c.events.map((e) => (
                  <li key={`${e.t}-${e.description}`}>
                    <code>{formatTimecode(e.t)}</code> {e.description}
                  </li>
                ))}
              </ul>
            </>
          )}
          {c.transcript_excerpt && (
            <>
              <h3>Transcription de l'extrait</h3>
              <p className="excerpt">{c.transcript_excerpt}</p>
            </>
          )}
        </div>
      )}
    </article>
  );
}
