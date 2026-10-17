import { defineConfig } from "@playwright/test";

// Runs the built UI (npm run build) against tests/e2e_server.py: a throwaway data dir and an
// in-memory AnkiConnect on port 18765.
export default defineConfig({
  testDir: "e2e",
  timeout: 60_000,
  workers: 1,
  use: { baseURL: "http://127.0.0.1:18710", browserName: "chromium", acceptDownloads: true },
  webServer: {
    command: "uv run python ../tests/e2e_server.py --port 18710 --anki-port 18765",
    url: "http://127.0.0.1:18710/api/documents",
    reuseExistingServer: false,
    timeout: 60_000,
  },
});
