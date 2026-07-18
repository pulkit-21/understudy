import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend (FastAPI, :8000) owns /api, the mock apps (/portal, /erp), and
// /docs. In dev we run the Vite server on :5173 and proxy those through, so the
// app is same-origin exactly as it is in production (where FastAPI serves the
// built assets). Build output goes to frontend/dist.
// Native dev talks to localhost; inside docker-compose the frontend container
// reaches the backend by its service name (VITE_BACKEND_URL=http://backend:8000).
const backend = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,   // listen on 0.0.0.0 so the port is reachable from the host
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
