import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The gateway serves the build at /demo, so every asset URL must start with /demo/.
// In `npm run dev` the page is at http://localhost:5173/demo/ and API calls are proxied to the
// gateway, which keeps them same-origin (no CORS) exactly like the built page.
const gateway = "http://localhost:8000";

export default defineConfig({
  base: "/demo/",
  plugins: [react()],
  server: {
    proxy: { "/v1": gateway, "/healthz": gateway },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
