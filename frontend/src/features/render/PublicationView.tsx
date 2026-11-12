import { useState } from "react";

export interface MusicSuggestion {
  mood: string;
  genre: string;
  tempo: string;
  search_keywords: string[];
  why: string;
  note: string;
}

export interface Publication {
  generated_by_ai: boolean;
  tiktok: { caption: string };
  youtube: { title: string; description: string };
  context: string;
  question: string;
  hashtags: string[];
  credits: string[];
  music_suggestion: MusicSuggestion | null;
  censored_words: number;
}

/** Bandeau : musique à ajouter soi-même à l'upload (jamais incrustée dans la vidéo). */
export function MusicBanner({ music }: { music: MusicSuggestion }) {
  return (
    <div className="alert music-banner" role="note" aria-label="Musique à ajouter à l'upload">
      <strong>🎵 Musique à ajouter à l'upload :</strong> {music.mood} · {music.genre} · tempo{" "}
      {music.tempo}. Rechercher : {music.search_keywords.map((k) => `« ${k} »`).join(", ")}.
      <span className="muted"> {music.why}</span>
      <p className="hint">{music.note}</p>
    </div>
  );
}

function CopyField({
  label,
  value,
  multiline,
}: {
  label: string;
  value: string;
  multiline?: boolean;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="copy-field">
      <div className="page-header">
        <strong>{label}</strong>
        <button
          type="button"
          className="btn btn-small"
          onClick={() => {
            void navigator.clipboard?.writeText(value).then(() => {
              setCopied(true);
              setTimeout(() => setCopied(false), 1500);
            });
          }}
        >
          {copied ? "Copié ✓" : "Copier"}
        </button>
      </div>
      {multiline ? (
        <textarea
          readOnly
          value={value}
          rows={Math.min(10, value.split("\n").length + 1)}
          aria-label={label}
        />
      ) : (
        <input readOnly value={value} aria-label={label} />
      )}
    </div>
  );
}

export function PublicationView({ pub }: { pub: Publication }) {
  return (
    <div className="publication">
      {!pub.generated_by_ai && (
        <p className="alert alert-warn" role="note">
          Textes minimaux construits sans IA : relisez-les avant de publier.
        </p>
      )}
      <CopyField label="TikTok — légende" value={pub.tiktok.caption} multiline />
      <CopyField label="YouTube Shorts — titre" value={pub.youtube.title} />
      <CopyField label="YouTube Shorts — description" value={pub.youtube.description} multiline />
      <p className="hint">
        Crédits ajoutés automatiquement ({pub.credits.length}) : obligatoires pour la voix CC BY et
        la source. {pub.censored_words > 0 && `${pub.censored_words} mot(s) grossier(s) masqué(s).`}
      </p>
    </div>
  );
}
