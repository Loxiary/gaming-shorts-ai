import { useState } from "react";

import { ErrorBox, Loading } from "../../components/Feedback";
import {
  type RuntimeSetting,
  type SettingValue,
  useRuntimeSettings,
  useSaveRuntime,
} from "../../services/adminApi";
import { errorMessage } from "../../services/api";

/** Réglages du .env modifiables ici ; appliqués par le worker au début du job suivant. */
export function RuntimeSettingsCard() {
  const settings = useRuntimeSettings();
  const save = useSaveRuntime();
  const [draft, setDraft] = useState<Record<string, SettingValue>>({});

  if (settings.isPending) return <Loading />;
  if (settings.isError) return <ErrorBox error={settings.error} />;
  const groups = [...new Set(settings.data.map((s) => s.group))];
  const changed = Object.keys(draft).length > 0;

  return (
    <form
      className="card"
      aria-label="Réglages globaux"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate(draft, { onSuccess: () => setDraft({}) });
      }}
    >
      <h2>Réglages globaux</h2>
      <p className="hint">
        Valeurs par défaut lues dans <code>.env</code> ; une valeur modifiée ici la remplace et
        s'applique au début du prochain job (jamais au milieu d'un traitement). « Rétablir » revient
        à la valeur du <code>.env</code>.
      </p>
      {groups.map((g) => (
        <fieldset key={g} className="weights-editor montage">
          <legend>{g}</legend>
          {settings.data
            .filter((s) => s.group === g)
            .map((s) => (
              <SettingField
                key={s.key}
                setting={s}
                value={draft[s.key] ?? s.value}
                onChange={(v) => setDraft((d) => ({ ...d, [s.key]: v }))}
                onReset={() => save.mutate({ [s.key]: null })}
              />
            ))}
        </fieldset>
      ))}
      {save.isError && (
        <p className="job-error" role="alert">
          {errorMessage(save.error)}
        </p>
      )}
      {save.isSuccess && !changed && (
        <p className="note" role="status">
          Réglages enregistrés : ils s'appliqueront au prochain job.
        </p>
      )}
      <div className="form-actions">
        <button type="button" className="btn" disabled={!changed} onClick={() => setDraft({})}>
          Annuler les modifications
        </button>
        <button type="submit" className="btn btn-primary" disabled={!changed || save.isPending}>
          {save.isPending ? "Enregistrement…" : "Enregistrer"}
        </button>
      </div>
    </form>
  );
}

function SettingField({
  setting: s,
  value,
  onChange,
  onReset,
}: {
  setting: RuntimeSetting;
  value: SettingValue;
  onChange: (v: SettingValue) => void;
  onReset: () => void;
}) {
  const id = `rs-${s.key}`;
  let input;
  if (s.type === "bool") {
    input = (
      <input
        id={id}
        type="checkbox"
        checked={Boolean(value)}
        onChange={(e) => onChange(e.target.checked)}
      />
    );
  } else if (s.type === "choice") {
    input = (
      <select id={id} value={String(value)} onChange={(e) => onChange(e.target.value)}>
        {s.choices.map((c) => (
          <option key={c} value={c}>
            {c}
          </option>
        ))}
      </select>
    );
  } else if (s.type === "int" || s.type === "float") {
    input = (
      <input
        id={id}
        type="number"
        min={s.min ?? undefined}
        max={s.max ?? undefined}
        step={s.type === "int" ? 1 : 0.5}
        value={String(value)}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    );
  } else {
    input = <input id={id} value={String(value)} onChange={(e) => onChange(e.target.value)} />;
  }
  return (
    <div className="runtime-setting">
      <label htmlFor={id}>{s.label}</label>
      {input}
      {s.overridden && (
        <>
          <span className="badge badge-demo" title={`Valeur du .env : ${String(s.env_value)}`}>
            modifié
          </span>
          <button type="button" className="btn btn-small btn-ghost" onClick={onReset}>
            Rétablir
          </button>
        </>
      )}
      <p className="hint">{s.help}</p>
    </div>
  );
}
