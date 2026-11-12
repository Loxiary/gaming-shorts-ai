import type { ProfileInput } from "../../services/analysisTypes";

/** Réglages audio et facecam par défaut d'un nouveau profil (alignés sur le backend). */
export const DEFAULT_AUDIO = {
  narration_mode: "auto",
  narration_voice: "fr_FR-siwis-medium",
  narration_speed: 1,
  narration_level_db: 0,
  game_level_db: 0,
  music_mode: "suggest",
  narration_title: true,
  react_overlay: true,
  bleep_profanity: true,
  music_level_db: -18,
  source_music_mode: "attenuate",
  source_music_reduction_db: 15,
  facecam_mode: "crop",
} satisfies Partial<ProfileInput>;

/** Transitions et effets ponctuels par défaut (Phase 7, alignés sur le backend). */
export const DEFAULT_EFFECTS = {
  effects_mode: "auto",
  transition_in: "zoom",
  transition_out: "fade",
  sfx_mode: "auto",
  sfx_level_db: -14,
} satisfies Partial<ProfileInput>;
