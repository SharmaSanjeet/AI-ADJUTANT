import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ command }) => ({
  base: command === "build" ? "/ui/" : "/",
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/incidents": "http://localhost:8010",
      "/audit": "http://localhost:8010",
    },
  },
  build: {
    outDir: "dist",
  },
}));
