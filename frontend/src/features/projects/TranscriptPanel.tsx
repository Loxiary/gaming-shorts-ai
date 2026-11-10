import { type RefObject, useMemo, useState } from "react";

import { ErrorBox, Loading } from "../../components/Feedback";
import { api } from "../../services/api";
import { formatTimecode } from "../../services/format";
import { useTranscript } from "../../services/queries";
import type { TranscriptSummary } from "../../services/types";

interface Props {
  projectId: string;
  summary: TranscriptSummary;
  mediaAvailable: boolean;
  videoRef: RefObject<HTMLVideoElement | null>;
}

export function TranscriptPanel({ projectId, summary, mediaAvailable, videoRef }: Props) {
  const transcript = useTranscript(projectId, true, summary.id);
  const [query, setQuery] = useState("");
  const [current, setCurrent] = useState(0);

  const segments = useMemo(() => {
    const all = transcript.data?.segments ?? [];
    const q = query.trim().toLowerCase();
    return q ? all.filter((s) => s.text.toLowerCase().includes(q)) : all;
  }, [transcript.data, query]);

  const seek = (seconds: number) => {
    const video = videoRef.current;
    if (!video) return;
    video.currentTime = seconds;
    void video.play().catch(() => undefined);
  };

  return (
    <div className="card">
      <h2>Transcription source</h2>
      <p className="muted">
        Transcription fidèle de l'audio d'origine (langue détectée :{" "}
        <strong>{summary.language ?? "?"}</strong>
        {summary.language_probability != null &&
          ` à ${Math.round(summary.language_probability * 100)} %`}
        ). {summary.segment_count} segments · {summary.engine}, modèle {summary.model} sur{" "}
        {summary.device === "cuda" ? "GPU" : "CPU"} ({summary.compute_type})
        {summary.processing_seconds != null && ` en ${Math.round(summary.processing_seconds)} s`}.
        Estimation automatique : des erreurs restent possibles.
      </p>

      <div className="transcript-layout">
        {mediaAvailable && (
          <video
            ref={videoRef}
            className="preview"
            src={api.mediaUrl(projectId)}
            controls
            preload="metadata"
            onTimeUpdate={(e) => setCurrent(e.currentTarget.currentTime)}
          />
        )}
        <div className="transcript">
          <input
            className="search"
            type="search"
            placeholder="Rechercher dans la transcription…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Rechercher dans la transcription"
          />
          {transcript.isPending && <Loading label="Chargement de la transcription…" />}
          {transcript.isError && (
            <ErrorBox error={transcript.error} onRetry={() => transcript.refetch()} />
          )}
          {transcript.data && segments.length === 0 && (
            <p className="muted">
              {query ? "Aucun segment ne correspond." : "Aucune parole détectée."}
            </p>
          )}
          <ol className="segments">
            {segments.map((s) => {
              const active = current >= s.start_seconds && current < s.end_seconds;
              return (
                <li key={s.position} className={active ? "segment active" : "segment"}>
                  {mediaAvailable ? (
                    <button
                      type="button"
                      className="timecode"
                      onClick={() => seek(s.start_seconds)}
                      title="Lire à partir de ce moment"
                    >
                      {formatTimecode(s.start_seconds)}
                    </button>
                  ) : (
                    <span className="timecode">{formatTimecode(s.start_seconds)}</span>
                  )}
                  <span>{s.text}</span>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
    </div>
  );
}
