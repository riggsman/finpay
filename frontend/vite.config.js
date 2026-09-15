import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The backend (FastAPI + Socket.IO) runs on :8000. We proxy REST and the
// Socket.IO endpoint so the browser talks to a single origin in development.
const BACKEND = process.env.VITE_BACKEND_URL || "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    proxy: {
      "/api": { target: BACKEND, changeOrigin: true },
      "/socket.io": { target: BACKEND, changeOrigin: true, ws: true },
    },
  },
});
