import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const isProd = mode === "production";
  return {
    plugins: [react()],
    server: {
      port: 5173,
      strictPort: true,
      proxy: {
        "/api": {
          target: "http://localhost:8000",
          changeOrigin: true,
        },
      },
    },
    build: {
      sourcemap: !isProd,
      outDir: "dist",
      assetsInlineLimit: 0,
      rollupOptions: {
        output: {
          manualChunks: undefined,
        },
      },
    },
  };
});
