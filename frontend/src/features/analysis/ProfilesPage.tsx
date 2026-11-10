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
import type { Criterion, Profile, ProfileInput } from "../../services/analysisTypes";
import { errorMessage } from "../../services/api";

function emptyProfile(criteria: Criterion[]): ProfileInput {
  return {
    name: "",
    description: null,
    editorial_focus: null,
    threshold: 60,
    weights: Object.fromEntries(criteria.map((c) => [c.key, 1])),
    output_language: "fr",
    min_duration: 61,
    max_duration: 180,
    max_candidates: 12,
    use_vision: true,
    is_default: false,
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
        l'angle éditorial transmis à l'IA et la durée des extraits (toujours entre 61 et 180 s).
      </p>

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
            Durée min (s)
            <input
              type="number"
              min={61}
              max={180}
              value={data.min_duration}
              onChange={(e) => set("min_duration", Number(e.target.value))}
            />
          </label>
          <label>
            Durée max (s)
            <input
              type="number"
              min={61}
              max={180}
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
