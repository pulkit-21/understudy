import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend (FastAPI, :8000) owns /api, the mock apps (/portal, /erp), and
// /docs. In dev we run the Vite server on :5173 and proxy those through, so the
// app is same-origin exactly as it is in production (where FastAPI serves the
// built assets). Build output goes to frontend/dist.
const backend = "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/portal": { target: backend, changeOrigin: true },
      "/erp": { target: backend, changeOrigin: true },
      "/healthz": { target: backend, changeOrigin: true },
      "/docs": { target: backend, changeOrigin: true },
      "/openapi.json": { target: backend, changeOrigin: true },
    },
  },
  build: { outDir: "dist", emptyOutDir: true },
});
