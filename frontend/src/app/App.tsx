import { type QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Link, Route, Routes } from "react-router";

import { Layout } from "../components/Layout";
import { CostsPage } from "../features/analysis/CostsPage";
import { ProfilesPage } from "../features/analysis/ProfilesPage";
import { ExportsPage } from "../features/render/ExportsPage";
import { DashboardPage } from "../features/dashboard/DashboardPage";
import { ImportPage } from "../features/import/ImportPage";
import { ProjectDetailPage } from "../features/projects/ProjectDetailPage";
import { ProjectsPage } from "../features/projects/ProjectsPage";
import { QueuePage } from "../features/queue/QueuePage";
import { SettingsPage } from "../features/settings/SettingsPage";

function NotFound() {
  return (
    <section>
      <h1>Page introuvable</h1>
      <Link to="/">Retour au tableau de bord</Link>
    </section>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<DashboardPage />} />
        <Route path="importer" element={<ImportPage />} />
        <Route path="projets" element={<ProjectsPage />} />
        <Route path="projets/:id" element={<ProjectDetailPage />} />
        <Route path="file" element={<QueuePage />} />
        <Route path="profils" element={<ProfilesPage />} />
        <Route path="couts" element={<CostsPage />} />
        <Route path="exports" element={<ExportsPage />} />
        <Route path="parametres" element={<SettingsPage />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}

export function App({ client }: { client: QueryClient }) {
  return (
    <QueryClientProvider client={client}>
      <AppRoutes />
    </QueryClientProvider>
  );
}
