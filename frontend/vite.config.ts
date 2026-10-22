import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies /api to the studio backend so the browser only ever talks
// to one origin (works behind the preview proxy, no CORS, no localhost calls
// from client code).
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    allowedHosts: true,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
  build: { outDir: "dist", sourcemap: false },
});
