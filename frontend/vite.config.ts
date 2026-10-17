import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../src/clanki/static", emptyOutDir: true, chunkSizeWarningLimit: 2000 },
  server: { proxy: { "/api": "http://127.0.0.1:8710" } },
  test: { include: ["src/**/*.test.ts"] },
});
