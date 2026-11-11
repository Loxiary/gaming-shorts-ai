import { RenderCard } from "./RenderCard";
import { ErrorBox } from "../../components/Feedback";
import { useRenders } from "../../services/renderApi";

export function RendersPanel({ projectId }: { projectId: string }) {
  const renders = useRenders(projectId);
  if (renders.isError) return <ErrorBox error={renders.error} />;
  if (!renders.data || renders.data.length === 0) return null;
  return (
    <div className="card">
      <h2>Shorts montés</h2>
      <p className="muted">
        Chaque short est vérifié (format, durée, son) puis accompagné d'un rapport de risques
        informatif. Rien n'est exporté sans votre confirmation.
      </p>
      <div className="render-list">
        {renders.data.map((r) => (
          <RenderCard key={r.id} render={r} />
        ))}
      </div>
    </div>
  );
}
