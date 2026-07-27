/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { TanStackRouterVite } from "@tanstack/router-plugin/vite";
import path from "path";

export default defineConfig({
  plugins: [
    tailwindcss(),
    TanStackRouterVite({
      routesDirectory: "./src/app/routes",
      generatedRouteTree: "./src/app/routeTree.gen.ts",
    }),
    react(),
  ],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: (id) => {
          if (id.includes("node_modules")) {
            if (id.includes("/react-dom/") || id.includes("/react/")) {
              return "vendor-react";
            }
            if (id.includes("@tanstack/react-router") || id.includes("@tanstack/router-")) {
              return "vendor-router";
            }
            if (id.includes("@tanstack/react-query") || id.includes("@tanstack/query-")) {
              return "vendor-query";
            }
            if (id.includes("@clerk/")) {
              return "vendor-clerk";
            }
            if (id.includes("recharts") || id.includes("victory-vendor") || id.includes("d3-")) {
              return "vendor-charts";
            }
          }
        },
      },
    },
  },
  server: {
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: "./src/test-setup.ts",
  },
});
