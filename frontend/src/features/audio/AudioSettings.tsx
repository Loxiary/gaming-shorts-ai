import type { ProfileInput } from "../../services/analysisTypes";
import { useAudioStatus } from "../../services/musicApi";

const FALLBACK_VOICES = [
  { id: "fr_FR-siwis-medium", label: "Français — SIWIS (femme)", present: true },
  { id: "en_US-joe-medium", label: "English — Joe (man)", present: true },
];

function db(value: number) {
  return `${value > 0 ? "+" : ""}${value} dB`;
}

export function AudioSettings({
  data,
  set,
}: {
  data: ProfileInput;
  set: <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) => void;
}) {
  const status = useAudioStatus();
  const voices = status.data?.assets?.filter((a) => a.is_voice) ?? FALLBACK_VOICES;
  const voiceLang = data.narration_voice.split("_")[0];

  return (
    <fieldset className="weights-editor montage">
      <legend>Audio et facecam</legend>
      <label>
        Musique d'origine
        <select
          value={data.source_music_mode}
          onChange={(e) =>
            set("source_music_mode", e.target.value as ProfileInput["source_music_mode"])
          }
        >
          <option value="attenuate">Détecter et atténuer (voix conservées)</option>
          <option value="detect">Détecter seulement (signalée dans le rapport)</option>
          <option value="off">Ne pas analyser</option>
        </select>
      </label>
      <label>
        Atténuation de la musique ({data.source_music_reduction_db} dB)
        <input
          type="range"
          min={3}
          max={40}
          value={data.source_music_reduction_db}
          disabled={data.source_music_mode !== "attenuate"}
          onChange={(e) => set("source_music_reduction_db", Number(e.target.value))}
        />
      </label>
      <label>
        Narration de synthèse
        <select
          value={data.narration_mode}
          onChange={(e) => set("narration_mode", e.target.value as ProfileInput["narration_mode"])}
        >
          <option value="auto">Titre lu au début + interventions de l'IA dans les silences</option>
          <option value="off">Jamais</option>
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.narration_title}
          disabled={data.narration_mode === "off"}
          onChange={(e) => set("narration_title", e.target.checked)}
        />
        La voix lit le titre au début du short
      </label>
      <label>
        Voix
        <select
          value={data.narration_voice}
          disabled={data.narration_mode === "off"}
          onChange={(e) => set("narration_voice", e.target.value)}
        >
          {voices.map((v) => (
            <option key={v.id} value={v.id}>
              {v.label}
              {v.present ? "" : " — non installée"}
            </option>
          ))}
        </select>
      </label>
      {data.narration_mode !== "off" && voiceLang !== data.output_language && (
        <p className="hint">
          La voix choisie ne parle pas la langue du profil ({data.output_language}) : une voix
          installée dans cette langue sera utilisée, sinon la narration sera abandonnée.
        </p>
      )}
      <label>
        Débit de la voix (×{data.narration_speed.toFixed(2)})
        <input
          type="range"
          min={0.7}
          max={1.4}
          step={0.05}
          value={data.narration_speed}
          disabled={data.narration_mode === "off"}
          onChange={(e) => set("narration_speed", Number(e.target.value))}
        />
      </label>
      <label>
        Musique ajoutée
        <select
          value={data.music_mode}
          onChange={(e) => set("music_mode", e.target.value as ProfileInput["music_mode"])}
        >
          <option value="suggest">
            Conseillée, à ajouter à l'upload (bibliothèque TikTok/YouTube)
          </option>
          <option value="library">
            Incrustée depuis ma bibliothèque locale (licence confirmée)
          </option>
          <option value="off">Aucune</option>
        </select>
      </label>
      <div className="colors">
        <label>
          Jeu ({db(data.game_level_db)})
          <input
            type="range"
            min={-30}
            max={10}
            value={data.game_level_db}
            onChange={(e) => set("game_level_db", Number(e.target.value))}
          />
        </label>
        <label>
          Narration ({db(data.narration_level_db)})
          <input
            type="range"
            min={-20}
            max={10}
            value={data.narration_level_db}
            onChange={(e) => set("narration_level_db", Number(e.target.value))}
          />
        </label>
        <label>
          Musique ({db(data.music_level_db)})
          <input
            type="range"
            min={-40}
            max={0}
            value={data.music_level_db}
            disabled={data.music_mode === "off"}
            onChange={(e) => set("music_level_db", Number(e.target.value))}
          />
        </label>
      </div>
      <p className="hint">
        Le jeu et la musique baissent automatiquement sous la narration et la parole ; le mélange
        final est normalisé à -14 LUFS.
      </p>
      <label>
        Facecam (webcam incrustée)
        <select
          value={data.facecam_mode}
          onChange={(e) => set("facecam_mode", e.target.value as ProfileInput["facecam_mode"])}
        >
          <option value="crop">Détecter et exclure par recadrage</option>
          <option value="off">Ne pas détecter</option>
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.react_overlay}
          onChange={(e) => set("react_overlay", e.target.checked)}
        />
        Facecam « réaction » ronde en haut à droite (vidéo commune en boucle, sans son ; cadrage
        dans Paramètres)
      </label>
    </fieldset>
  );
}
