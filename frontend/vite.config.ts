import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Vite dev proxy keeps local development same-origin.
// The backend exposes no CORS middleware, so `/api` is forwarded
// to the local FastAPI server instead of calling it cross-origin.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
  },
});
