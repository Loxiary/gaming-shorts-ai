import { NavLink, Outlet } from "react-router";

import { useHealth } from "../services/queries";

const NAV = [
  { to: "/", label: "Tableau de bord", end: true },
  { to: "/importer", label: "Importer", end: false },
  { to: "/projets", label: "Bibliothèque", end: false },
  { to: "/file", label: "File d'attente", end: false },
  { to: "/profils", label: "Profils", end: false },
  { to: "/couts", label: "Coûts API", end: false },
  { to: "/parametres", label: "Paramètres", end: false },
];

function BackendStatus() {
  const health = useHealth();
  if (health.isPending) return <span className="pill pill-neutral">Connexion…</span>;
  if (health.isError) return <span className="pill pill-error">Backend injoignable</span>;
  if (health.data.database !== "ok")
    return <span className="pill pill-error">Base non migrée</span>;
  return (
    <>
      <span className="pill pill-ok">Backend connecté</span>
      {health.data.worker.alive ? (
        <span className="pill pill-ok">Worker actif</span>
      ) : (
        <span
          className="pill pill-warn"
          title="Les jobs restent en attente tant que le worker est arrêté"
        >
          Worker arrêté
        </span>
      )}
    </>
  );
}

export function Layout() {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-logo" aria-hidden="true">
            ▶
          </span>
          <span>
            Gaming Shorts <strong>AI</strong>
          </span>
        </div>
        <nav aria-label="Navigation principale">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="main">
        <header className="topbar">
          <div className="phase-banner" role="note">
            <strong>Phase 3.</strong> Import, transcription et détection des clips disponibles. Le
            montage vidéo, les sous-titres et l'export ne sont{" "}
            <strong>pas encore implémentés</strong>.
          </div>
          <div className="status-pills" aria-live="polite">
            <BackendStatus />
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
