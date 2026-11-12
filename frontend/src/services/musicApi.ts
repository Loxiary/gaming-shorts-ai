// Phase 5 : bibliothèque musicale locale et état des modèles audio / facecam.
// Aligné sur backend/app/schemas/music.py.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { request } from "./api";

const enc = encodeURIComponent;

export interface MusicTrack {
  id: string;
  file_path: string;
  file_name: string;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  title: string | null;
  artist: string | null;
  license: string | null;
  source_url: string | null;
  moods: string[];
  notes: string | null;
  license_confirmed: boolean;
  usable: boolean;
  audio_url: string;
}

export type MusicTrackInput = Pick<
  MusicTrack,
  "title" | "artist" | "license" | "source_url" | "moods" | "notes" | "license_confirmed"
>;

export interface MusicScan {
  added: number;
  removed: number;
  total: number;
  errors: string[];
  folder: string;
}

export interface AudioAsset {
  id: string;
  label: string;
  purpose: string;
  size_mb: number;
  license: string;
  credit: string | null;
  present: boolean;
  is_voice: boolean;
  language: string | null;
}

export interface AudioStatus {
  assets: AudioAsset[];
  moods: string[];
  music_folder: string;
  download_command: string;
}

export const musicApi = {
  list: () => request<MusicTrack[]>("GET", "/api/music"),
  scan: () => request<MusicScan>("POST", "/api/music/scan"),
  update: (id: string, data: MusicTrackInput) =>
    request<MusicTrack>("PATCH", `/api/music/${enc(id)}`, data),
  status: () => request<AudioStatus>("GET", "/api/audio/status"),
};

export const useMusic = () => useQuery({ queryKey: ["music"], queryFn: musicApi.list });
export const useAudioStatus = () =>
  useQuery({ queryKey: ["audio-status"], queryFn: musicApi.status, staleTime: 60_000 });

export function useScanMusic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: musicApi.scan,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["music"] }),
  });
}

export function useUpdateMusic() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: MusicTrackInput }) => musicApi.update(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["music"] }),
  });
}
