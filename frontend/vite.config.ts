import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Le frontend appelle l'API via /api, relayé vers le backend local (127.0.0.1 uniquement).
const apiTarget = process.env.GSA_API_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 5173,
    strictPort: true,
    proxy: { "/api": { target: apiTarget, changeOrigin: false } },
  },
  preview: { host: "127.0.0.1", port: 4173, strictPort: true },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
