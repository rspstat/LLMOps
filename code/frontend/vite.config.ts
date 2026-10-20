import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The gateway serves the build at its root (`/`, `/assets/*`, `/theme-init.js`).
// In `npm run dev` the page is at http://localhost:5173/ and API calls are proxied to the
// gateway, which keeps them same-origin (no CORS) exactly like the built page.
const gateway = "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: { "/v1": gateway, "/healthz": gateway },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
