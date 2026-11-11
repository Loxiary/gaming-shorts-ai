import type { ProfileInput } from "../../services/analysisTypes";

export function EffectsSettings({
  data,
  set,
}: {
  data: ProfileInput;
  set: <K extends keyof ProfileInput>(key: K, value: ProfileInput[K]) => void;
}) {
  return (
    <fieldset className="weights-editor montage">
      <legend>Transitions et effets ponctuels</legend>
      <label>
        Effets (flash, tremblement)
        <select
          value={data.effects_mode}
          onChange={(e) => set("effects_mode", e.target.value as ProfileInput["effects_mode"])}
        >
          <option value="auto">Sur les moments forts choisis par l'IA (4 au plus)</option>
          <option value="off">Aucun</option>
        </select>
      </label>
      <label>
        Transition d'entrée
        <select
          value={data.transition_in}
          onChange={(e) => set("transition_in", e.target.value as ProfileInput["transition_in"])}
        >
          <option value="zoom">Zoom d'ouverture</option>
          <option value="fade">Fondu depuis le noir</option>
          <option value="none">Aucune</option>
        </select>
      </label>
      <label>
        Transition de sortie
        <select
          value={data.transition_out}
          onChange={(e) => set("transition_out", e.target.value as ProfileInput["transition_out"])}
        >
          <option value="fade">Fondu au noir (texte final lisible)</option>
          <option value="none">Aucune</option>
        </select>
      </label>
      <label>
        Bruitages
        <select
          value={data.sfx_mode}
          onChange={(e) => set("sfx_mode", e.target.value as ProfileInput["sfx_mode"])}
        >
          <option value="auto">Souffle et impact sur les effets (synthétisés, sans licence)</option>
          <option value="off">Aucun</option>
        </select>
      </label>
      <label>
        Niveau des bruitages ({data.sfx_level_db} dB)
        <input
          type="range"
          min={-40}
          max={0}
          value={data.sfx_level_db}
          disabled={data.sfx_mode === "off"}
          onChange={(e) => set("sfx_level_db", Number(e.target.value))}
        />
      </label>
      <p className="hint">
        Sans IA, aucun effet n'est ajouté ; les transitions s'appliquent toujours. Les textes
        (accroche, sous-titres) ne sont jamais affectés par les effets.
      </p>
    </fieldset>
  );
}
