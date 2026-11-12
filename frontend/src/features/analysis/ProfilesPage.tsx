import { useState } from "react";

import { ConfirmDialog } from "../../components/ConfirmDialog";
import { ErrorBox, Loading } from "../../components/Feedback";
import {
  useCriteria,
  useDeleteProfile,
  useDuplicateProfile,
  useProfiles,
  useSaveProfile,
} from "../../services/analysisApi";
import type { Criterion, Profile, ProfileInput, SubtitleStyle } from "../../services/analysisTypes";
import { adminApi, useImportProfiles } from "../../services/adminApi";
import { errorMessage } from "../../services/api";
import { AudioSettings } from "../audio/AudioSettings";
import { DEFAULT_AUDIO, DEFAULT_EFFECTS } from "../audio/audioDefaults";
import { EffectsSettings } from "../audio/EffectsSettings";

function emptyProfile(criteria: Criterion[]): ProfileInput {
  return {
    name: "",
    description: null,
    editorial_focus: null,
    threshold: 60,
    weights: Object.fromEntries(criteria.map((c) => [c.key, 1])),
    output_language: "fr",
    min_duration: 61,
    max_duration: 90,
    max_candidates: 12,
    use_vision: true,
    is_default: false,
    subtitle_mode: "source",
    subtitle_style: { ...DEFAULT_STYLE },
    layout: "focus",
    jump_zoom: true,
    progress_bar: true,
    zoom_intensity: 0.12,
    hook_enabled: true,
    cta_enabled: true,
    cta_text: null,
    render_encoder: "libx264",
    censor_profanity: true,
    min_confidence: 0.5,
    ...DEFAULT_AUDIO,
    ...DEFAULT_EFFECTS,
  };
}

function toInput(p: Profile): ProfileInput {
  const { id: _id, created_at: _c, updated_at: _u, ...rest } = p;
  void _id;
  void _c;
  void _u;
  return rest;
}

export function ProfilesPage() {
  const profiles = useProfiles();
  const criteria = useCriteria();
  const duplicate = useDuplicateProfile();
  const remove = useDeleteProfile();
  const [editing, setEditing] = useState<{ id: string | null; data: ProfileInput } | null>(null);
  const [toDelete, setToDelete] = useState<Profile | null>(null);

  if (profiles.isPending || criteria.isPending) return <Loading />;
  if (profiles.isError)
    return <ErrorBox error={profiles.error} onRetry={() => profiles.refetch()} />;
  if (criteria.isError) return <ErrorBox error={criteria.error} />;

  return (
    <section>
      <div className="page-header">
        <h1>Profils de montage</h1>
        {!editing && (
          <button
            type="button"
            className="btn btn-primary"
            onClick={() => setEditing({ id: null, data: emptyProfile(criteria.data) })}
          >
            Nouveau profil
          </button>
        )}
      </div>
      <p className="muted">
        Un profil fixe le seuil de sélection, l'importance de chaque critère dans la note globale,
        l'angle éditorial transmis à l'IA et la durée des extraits (toujours entre 61 et 90 s).
      </p>

      <ProfilesTransfer />

      {editing && (
        <ProfileEditor
          key={editing.id ?? "new"}
          id={editing.id}
          initial={editing.data}
          criteria={criteria.data}
          onDone={() => setEditing(null)}
        />
      )}

      {(duplicate.isError || remove.isError) && (
        <p className="job-error" role="alert">
          {errorMessage(duplicate.error ?? remove.error)}
        </p>
      )}

      <div className="profile-list">
        {profiles.data.map((p) => (
          <article key={p.id} className="card profile" aria-label={`Profil ${p.name}`}>
            <div className="page-header">
              <h2>
                {p.name} {p.is_default && <span className="badge badge-completed">Par défaut</span>}
              </h2>
              <div className="job-actions">
                <button
                  type="button"
                  className="btn btn-small"
                  onClick={() => setEditing({ id: p.id, data: toInput(p) })}
                >
                  Modifier
                </button>
                <button
                  type="button"
                  className="btn btn-small"
                  disabled={duplicate.isPending}
                  onClick={() => duplicate.mutate(p.id)}
                >
                  Dupliquer
                </button>
                {!p.is_default && (
                  <button
                    type="button"
                    className="btn btn-small btn-danger"
                    onClick={() => setToDelete(p)}
                  >
                    Supprimer
                  </button>
                )}
              </div>
            </div>
            {p.description && <p className="muted">{p.description}</p>}
            <p className="hint">
              Seuil {p.threshold}/100 · extraits de {p.min_duration} à {p.max_duration} s ·{" "}
              {p.max_candidates} candidats max · langue {p.output_language} · images{" "}
              {p.use_vision ? "envoyées à l'IA" : "non envoyées"}
            </p>
            <ul className="weights">
              {criteria.data.map((c) => (
                <li key={c.key}>
                  {c.label} <strong>×{p.weights[c.key]?.toFixed(1)}</strong>
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>

      {toDelete && (
        <ConfirmDialog
          title="Supprimer ce profil ?"
          danger
          confirmLabel="Supprimer"
          pending={remove.isPending}
          message={
            <p>
              Le profil <strong>{toDelete.name}</strong> sera supprimé. Les analyses déjà faites
              avec lui gardent une copie de ses réglages.
            </p>
          }
          onCancel={() => setToDelete(null)}
          onConfirm={() => remove.mutate(toDelete.id, { onSuccess: () => setToDelete(null) })}
        />
      )}
    </section>
  );
}

function ProfileEditor({
  id,
  initial,
  criteria,
  onDone,
}: {
  id: string | null;
  initial: ProfileInput;
  criteria: Criterion[];
  onDone: () => void;
}) {
  const [data, setData] = useState<ProfileInput>(initial);
  const save = useSaveProfile();
  const set = <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) =>
    setData((d) => ({ ...d, [key]: value }));

  return (
    <div className="card">
      <h2>{id ? "Modifier le profil" : "Nouveau profil"}</h2>
      <form
        className="form form-wide"
        noValidate
        onSubmit={(e) => {
          e.preventDefault();
          save.mutate({ id, data }, { onSuccess: onDone });
        }}
      >
        <label>
          Nom *
          <input value={data.name} maxLength={120} onChange={(e) => set("name", e.target.value)} />
        </label>
        <label>
          Description
          <input
            value={data.description ?? ""}
            maxLength={2000}
            onChange={(e) => set("description", e.target.value || null)}
          />
        </label>
        <label>
          Angle éditorial (transmis à l'IA)
          <textarea
            rows={3}
            maxLength={2000}
            value={data.editorial_focus ?? ""}
            onChange={(e) => set("editorial_focus", e.target.value || null)}
          />
        </label>
        <div className="form-row">
          <label>
            Seuil de sélection (0–100)
            <input
              type="number"
              min={0}
              max={100}
              value={data.threshold}
              onChange={(e) => set("threshold", Number(e.target.value))}
            />
          </label>
          <label>
            Confiance minimale (0–1)
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={data.min_confidence}
              onChange={(e) => set("min_confidence", Number(e.target.value))}
              title="Un extrait noté par l'IA avec une confiance plus faible n'est pas sélectionné"
            />
          </label>
          <label>
            Durée min (s)
            <input
              type="number"
              min={61}
              max={90}
              value={data.min_duration}
              onChange={(e) => set("min_duration", Number(e.target.value))}
            />
          </label>
          <label>
            Durée max (s)
            <input
              type="number"
              min={61}
              max={90}
              value={data.max_duration}
              onChange={(e) => set("max_duration", Number(e.target.value))}
            />
          </label>
          <label>
            Candidats max
            <input
              type="number"
              min={1}
              max={50}
              value={data.max_candidates}
              onChange={(e) => set("max_candidates", Number(e.target.value))}
            />
          </label>
          <label>
            Langue des explications
            <select
              value={data.output_language}
              onChange={(e) => set("output_language", e.target.value)}
            >
              <option value="fr">Français</option>
              <option value="en">Anglais</option>
            </select>
          </label>
        </div>
        <fieldset className="weights-editor">
          <legend>Importance des critères dans la note globale (0 = ignoré, 5 = maximal)</legend>
          {criteria.map((c) => (
            <label key={c.key}>
              <span>
                {c.label} <strong>×{(data.weights[c.key] ?? 1).toFixed(1)}</strong>
              </span>
              <input
                type="range"
                min={0}
                max={5}
                step={0.1}
                value={data.weights[c.key] ?? 1}
                onChange={(e) =>
                  set("weights", { ...data.weights, [c.key]: Number(e.target.value) })
                }
              />
            </label>
          ))}
        </fieldset>
        <label className="checkbox">
          <input
            type="checkbox"
            checked={data.use_vision}
            onChange={(e) => set("use_vision", e.target.checked)}
          />
          Envoyer des images de chaque extrait à l'IA
        </label>
        <MontageSettings data={data} set={set} />
        <AudioSettings data={data} set={set} />
        <EffectsSettings data={data} set={set} />
        <label className="checkbox">
          <input
            type="checkbox"
            checked={data.is_default}
            onChange={(e) => set("is_default", e.target.checked)}
          />
          Profil par défaut
        </label>
        {save.isError && (
          <p className="job-error" role="alert">
            {errorMessage(save.error)}
          </p>
        )}
        <div className="form-actions">
          <button type="button" className="btn" onClick={onDone}>
            Annuler
          </button>
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? "Enregistrement…" : "Enregistrer"}
          </button>
        </div>
      </form>
    </div>
  );
}

const DEFAULT_STYLE: SubtitleStyle = {
  font: "Arial Black",
  size: 76,
  text_color: "#FFFFFF",
  highlight_color: "#FFE500",
  keyword_color: "#38E1FF",
  uppercase: true,
  max_words: 3,
};

const FONTS = ["Arial Black", "Impact", "Segoe UI Black", "Bahnschrift", "Verdana"];

function MontageSettings({
  data,
  set,
}: {
  data: ProfileInput;
  set: <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) => void;
}) {
  const style = data.subtitle_style;
  const setStyle = <K extends keyof SubtitleStyle>(key: K, value: SubtitleStyle[K]) =>
    set("subtitle_style", { ...style, [key]: value });

  return (
    <fieldset className="weights-editor montage">
      <legend>Montage du short</legend>
      <label>
        Sous-titres
        <select
          value={data.subtitle_mode}
          onChange={(e) => set("subtitle_mode", e.target.value as ProfileInput["subtitle_mode"])}
        >
          <option value="source">Langue d'origine (verbatim)</option>
          <option value="translate">Traduits dans la langue du profil (IA)</option>
          <option value="off">Aucun</option>
        </select>
      </label>
      <label>
        Police
        <select value={style.font} onChange={(e) => setStyle("font", e.target.value)}>
          {FONTS.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
      </label>
      <label>
        Taille ({style.size})
        <input
          type="range"
          min={40}
          max={120}
          value={style.size}
          onChange={(e) => setStyle("size", Number(e.target.value))}
        />
      </label>
      <label>
        Mots par ligne ({style.max_words})
        <input
          type="range"
          min={1}
          max={6}
          value={style.max_words}
          onChange={(e) => setStyle("max_words", Number(e.target.value))}
        />
      </label>
      <div className="colors">
        <label>
          Texte
          <input
            type="color"
            value={style.text_color}
            onChange={(e) => setStyle("text_color", e.target.value.toUpperCase())}
          />
        </label>
        <label>
          Mot prononcé
          <input
            type="color"
            value={style.highlight_color}
            onChange={(e) => setStyle("highlight_color", e.target.value.toUpperCase())}
          />
        </label>
        <label>
          Mots clés
          <input
            type="color"
            value={style.keyword_color}
            onChange={(e) => setStyle("keyword_color", e.target.value.toUpperCase())}
          />
        </label>
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={style.uppercase}
          onChange={(e) => setStyle("uppercase", e.target.checked)}
        />
        Sous-titres en majuscules
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.censor_profanity}
          onChange={(e) => set("censor_profanity", e.target.checked)}
        />
        Masquer les mots grossiers dans les textes (« pu**** »)
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.bleep_profanity}
          onChange={(e) => set("bleep_profanity", e.target.checked)}
        />
        Bip sonore sur les mots grossiers prononcés
      </label>
      <label>
        Disposition
        <select
          value={data.layout}
          onChange={(e) => set("layout", e.target.value as ProfileInput["layout"])}
        >
          <option value="focus">Gros plan carré qui suit le visage (recommandé)</option>
          <option value="blur">Gameplay entier sur fond flouté</option>
          <option value="fill">Plein cadre (bords du gameplay coupés)</option>
        </select>
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.jump_zoom}
          onChange={(e) => set("jump_zoom", e.target.checked)}
        />
        Rythme : recadrage franc à chaque changement de phrase (toutes les 3,5 s au moins)
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.progress_bar}
          onChange={(e) => set("progress_bar", e.target.checked)}
        />
        Barre de progression en haut de l'écran
      </label>
      <label>
        Intensité des zooms ({Math.round(data.zoom_intensity * 100)} %)
        <input
          type="range"
          min={0}
          max={0.5}
          step={0.01}
          value={data.zoom_intensity}
          onChange={(e) => set("zoom_intensity", Number(e.target.value))}
        />
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.hook_enabled}
          onChange={(e) => set("hook_enabled", e.target.checked)}
        />
        Accroche au début
      </label>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={data.cta_enabled}
          onChange={(e) => set("cta_enabled", e.target.checked)}
        />
        Appel à l'action à la fin
      </label>
      <label>
        Texte de l'appel à l'action (vide = proposé par l'IA)
        <input
          value={data.cta_text ?? ""}
          maxLength={200}
          disabled={!data.cta_enabled}
          onChange={(e) => set("cta_text", e.target.value || null)}
        />
      </label>
      <label>
        Encodage
        <select
          value={data.render_encoder}
          onChange={(e) => set("render_encoder", e.target.value as ProfileInput["render_encoder"])}
        >
          <option value="libx264">Processeur (libx264)</option>
          <option value="h264_nvenc">Carte graphique NVIDIA (NVENC)</option>
        </select>
      </label>
    </fieldset>
  );
}

/** Export (fichier JSON) et import des profils, pour les sauvegarder ou les partager. */
function ProfilesTransfer() {
  const importer = useImportProfiles();
  const [readError, setReadError] = useState<string | null>(null);
  return (
    <div className="job-actions profiles-transfer">
      <a className="btn btn-small" href={adminApi.profilesExportUrl} download>
        Exporter les profils
      </a>
      <label className="btn btn-small">
        Importer des profils…
        <input
          type="file"
          accept="application/json,.json"
          className="visually-hidden"
          aria-label="Fichier de profils à importer"
          onChange={async (e) => {
            const file = e.target.files?.[0];
            e.target.value = "";
            if (!file) return;
            setReadError(null);
            try {
              importer.mutate(JSON.parse(await file.text()));
            } catch {
              setReadError("Fichier illisible : choisissez un export de profils (JSON).");
            }
          }}
        />
      </label>
      {(readError || importer.isError) && (
        <span className="job-error" role="alert">
          {readError ?? errorMessage(importer.error)}
        </span>
      )}
      {importer.data && (
        <span className="note" role="status">
          {importer.data.length} profil(s) importé(s) :{" "}
          {importer.data.map((p) => p.name).join(", ")}.
        </span>
      )}
    </div>
  );
}
