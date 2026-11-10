import type { JobStatus, RightsStatus, StepStatus } from "./types";

const dateFormatter = new Intl.DateTimeFormat("fr-FR", {
  dateStyle: "short",
  timeStyle: "medium",
});

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : dateFormatter.format(d);
}

export function formatDuration(startIso: string | null, endIso: string | null): string {
  if (!startIso) return "—";
  const start = new Date(startIso).getTime();
  const end = endIso ? new Date(endIso).getTime() : Date.now();
  const seconds = Math.max(0, Math.round((end - start) / 1000));
  if (seconds < 60) return `${seconds} s`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} min ${String(seconds % 60).padStart(2, "0")} s`;
}

export function formatBytes(bytes: number): string {
  const units = ["o", "Ko", "Mo", "Go", "To"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toLocaleString("fr-FR", { maximumFractionDigits: unit === 0 ? 0 : 1 })} ${units[unit]}`;
}

export function formatTimecode(seconds: number | null | undefined): string {
  if (seconds == null || Number.isNaN(seconds)) return "—";
  const total = Math.max(0, Math.floor(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const mm = String(m).padStart(h ? 2 : 1, "0");
  return `${h ? `${h}:` : ""}${mm}:${String(s).padStart(2, "0")}`;
}

export const RIGHTS_LABELS: Record<RightsStatus, string> = {
  unknown: "Inconnu / non vérifié",
  owned: "Je suis le créateur de la vidéo",
  authorized: "Autorisation obtenue du créateur",
  licensed: "Licence permettant la réutilisation (ex. Creative Commons)",
};

export const JOB_STATUS_LABELS: Record<JobStatus, string> = {
  queued: "En attente",
  running: "En cours",
  completed: "Terminé",
  failed: "Échec",
  cancelled: "Annulé",
};

export const STEP_STATUS_LABELS: Record<StepStatus, string> = {
  pending: "À faire",
  running: "En cours",
  completed: "Terminée",
  failed: "Échec",
  cancelled: "Annulée",
};
