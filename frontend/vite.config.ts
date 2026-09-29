import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Bound JSDOM concurrency on developer machines; keep the normal test timeout.
  test: { environment: "jsdom", maxWorkers: 2, minWorkers: 1 },
});
