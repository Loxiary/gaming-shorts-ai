import { ApiError, errorMessage } from "../services/api";

export function Loading({ label = "Chargement…" }: { label?: string }) {
  return (
    <p className="muted" role="status" aria-live="polite">
      <span className="spinner" aria-hidden="true" /> {label}
    </p>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const offline = error instanceof ApiError && error.kind === "network";
  return (
    <div className="alert alert-error" role="alert">
      <strong>{offline ? "Backend injoignable" : "Erreur"}</strong>
      <span>{errorMessage(error)}</span>
      {onRetry && (
        <button type="button" className="btn btn-small" onClick={onRetry}>
          Réessayer
        </button>
      )}
    </div>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return <div className="empty">{children}</div>;
}
