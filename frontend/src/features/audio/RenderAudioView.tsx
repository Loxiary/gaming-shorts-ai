import { formatTimecode } from "../../services/format";
import type { AudioReport, Credit, FacecamResult } from "../../services/renderApi";

const SOURCE_MUSIC: Record<string, string> = {
  disabled: "Analyse désactivée (profil)",
  unavailable: "Non analysée (modèle absent)",
  none: "Aucune musique détectée",
  detected: "Musique détectée",
};

const NARRATION: Record<string, string> = {
  disabled: "Désactivée (profil)",
  skipped: "Non proposée (plan sans IA)",
  not_needed: "Jugée inutile par l'IA",
  unavailable: "Indisponible (voix absente)",
  added: "Ajoutée",
  dropped: "Abandonnée (aucun silence assez long)",
};

const MUSIC: Record<string, string> = {
  disabled: "Désactivée (profil)",
  skipped: "Non ajoutée : musique d'origine conservée",
  not_needed: "Jugée inutile par l'IA",
  empty_library: "Aucun morceau utilisable dans la bibliothèque",
  added: "Ajoutée",
  error: "Morceau illisible",
};

const FACECAM: Record<string, string> = {
  disabled: "Détection désactivée (profil)",
  unavailable: "Non vérifié (détecteur absent)",
  none: "Aucun facecam détecté",
  uncertain: "Détection incertaine — aucun recadrage",
  detected: "Facecam détecté et exclu par recadrage",
  detected_not_cropped: "Facecam détecté mais non exclu",
};

const pct = (v: number | undefined) => `${Math.round((v ?? 0) * 100)} %`;

export function RenderAudioView({
  audio,
  facecam,
  credits,
  previewUrl,
}: {
  audio: AudioReport | null | undefined;
  facecam: FacecamResult | null | undefined;
  credits: Credit[];
  previewUrl: string | null | undefined;
}) {
  const sm = audio?.source_music;
  return (
    <div className="audio-view">
      {previewUrl && (
        <label className="audio-preview">
          Aperçu du mixage audio (niveau final)
          <audio controls preload="none" src={previewUrl} />
        </label>
      )}
      <dl className="details">
        <div>
          <dt>Facecam</dt>
          <dd>
            {facecam ? (FACECAM[facecam.status] ?? facecam.status) : "—"}
            {facecam?.status === "detected" && facecam.crop && (
              <span className="muted">
                {" "}
                (bord {facecam.crop_side}, {pct(facecam.loss)} de l'image retirée)
              </span>
            )}
            {facecam?.warning && <span className="job-error"> ⚠ {facecam.warning}</span>}
          </dd>
        </div>
        <div>
          <dt>Musique d'origine</dt>
          <dd>
            {sm ? (SOURCE_MUSIC[sm.status] ?? sm.status) : "—"}
            {sm?.status === "detected" && (
              <span className="muted">
                {" "}
                sur {pct(sm.ratio)} de l'extrait
                {sm.attenuated
                  ? ` · atténuée de ${sm.reduction_db} dB · résiduelle : ${pct(sm.residual_ratio)}`
                  : " · conservée"}
              </span>
            )}
            {sm?.per_second && sm.per_second.length > 0 && <MusicStrip values={sm.per_second} />}
          </dd>
        </div>
        <div>
          <dt>Narration</dt>
          <dd>
            {audio ? (NARRATION[audio.narration.status] ?? audio.narration.status) : "—"}
            {audio?.narration.reason && <span className="muted"> — {audio.narration.reason}</span>}
            {audio && audio.narration.lines.length > 0 && (
              <ul className="plain">
                {audio.narration.lines.map((l) => (
                  <li key={`${l.t}-${l.text}`}>
                    <code>{formatTimecode(l.t)}</code> « {l.text} »
                    {l.moved && <span className="muted"> (décalée dans un silence)</span>}
                  </li>
                ))}
              </ul>
            )}
          </dd>
        </div>
        {audio?.sfx && (
          <div>
            <dt>Bruitages</dt>
            <dd>
              {audio.sfx.status === "added"
                ? `${audio.sfx.events?.length ?? 0} bruitage(s) synthétisé(s) à ${audio.sfx.level_db} dB : ` +
                  (audio.sfx.events ?? [])
                    .map(
                      (e) => `${e.kind === "impact" ? "impact" : "souffle"} ${formatTimecode(e.t)}`,
                    )
                    .join(", ")
                : audio.sfx.status === "none"
                  ? "Aucun (ni effet ni transition sonore)"
                  : "Désactivés (profil)"}
            </dd>
          </div>
        )}
        <div>
          <dt>Musique ajoutée</dt>
          <dd>
            {audio ? (MUSIC[audio.music.status] ?? audio.music.status) : "—"}
            {audio?.music.status === "added" && (
              <span className="muted">
                {" "}
                : « {audio.music.title} »{audio.music.artist ? ` — ${audio.music.artist}` : ""} (
                {audio.music.license}){audio.music.mood ? ` · ambiance ${audio.music.mood}` : ""}
              </span>
            )}
          </dd>
        </div>
        {credits.length > 0 && (
          <div>
            <dt>Crédits à publier</dt>
            <dd>
              <ul className="plain">
                {credits.map((c) => (
                  <li key={c.text}>{c.text}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
        {audio && audio.notes.length > 0 && (
          <div>
            <dt>Remarques</dt>
            <dd>
              <ul className="warnings">
                {audio.notes.map((n) => (
                  <li key={n}>⚠ {n}</li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>
    </div>
  );
}

/** Probabilité de musique seconde par seconde (barres). */
function MusicStrip({ values }: { values: number[] }) {
  return (
    <div
      className="music-strip"
      role="img"
      aria-label={`Musique détectée seconde par seconde (${values.length} s)`}
    >
      {values.map((v, i) => (
        <span
          key={i}
          style={{ height: `${Math.max(4, v * 100)}%` }}
          className={v >= 0.4 ? "on" : ""}
        />
      ))}
    </div>
  );
}
