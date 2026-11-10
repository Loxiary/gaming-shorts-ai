import { useState } from "react";

import { errorMessage } from "../../services/api";
import type { ProjectCreate } from "../../services/types";

interface Props {
  initial?: { name: string; game: string | null; description: string | null };
  submitLabel: string;
  pending: boolean;
  error: unknown;
  showTestFlag?: boolean;
  onSubmit: (data: ProjectCreate) => void;
  onCancel?: () => void;
}

export function ProjectForm({
  initial,
  submitLabel,
  pending,
  error,
  showTestFlag = false,
  onSubmit,
  onCancel,
}: Props) {
  const [name, setName] = useState(initial?.name ?? "");
  const [game, setGame] = useState(initial?.game ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [isTest, setIsTest] = useState(true);
  const [localError, setLocalError] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) {
      setLocalError("Le nom du projet est obligatoire.");
      return;
    }
    setLocalError(null);
    onSubmit({
      name: name.trim(),
      game: game.trim() || null,
      description: description.trim() || null,
      ...(showTestFlag ? { is_test: isTest } : {}),
    });
  };

  const shownError = localError ?? (error ? errorMessage(error) : null);

  return (
    <form className="form" onSubmit={submit} noValidate>
      <label>
        Nom du projet *
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={200}
          placeholder="Ex. GTA 6 — session du 10/11"
        />
      </label>
      <label>
        Jeu
        <input
          value={game}
          onChange={(e) => setGame(e.target.value)}
          maxLength={120}
          placeholder="Ex. GTA 6"
        />
      </label>
      <label>
        Description
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={5000}
          rows={3}
        />
      </label>
      {showTestFlag && (
        <label className="checkbox">
          <input type="checkbox" checked={isTest} onChange={(e) => setIsTest(e.target.checked)} />
          Projet de test
        </label>
      )}
      {shownError && (
        <p className="job-error" role="alert">
          {shownError}
        </p>
      )}
      <div className="form-actions">
        {onCancel && (
          <button type="button" className="btn" onClick={onCancel}>
            Annuler
          </button>
        )}
        <button type="submit" className="btn btn-primary" disabled={pending}>
          {pending ? "Enregistrement…" : submitLabel}
        </button>
      </div>
    </form>
  );
}
