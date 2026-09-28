import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

import { buildVersion } from "./dev/buildVersion";
import { densifyCloudPlugin } from "./dev/densifyCloudPlugin";

const BACKEND_DEV_URL = process.env.VITE_BACKEND_DEV_URL ?? "http://127.0.0.1:8000";
const PROJECT_FILE = new URL("../pyproject.toml", import.meta.url);

export default defineConfig({
    define: {
        __BUILD_VERSION__: JSON.stringify(
            buildVersion(PROJECT_FILE, process.env.SAMPLERIPPER_BUILD_COMMIT, new Date()),
        ),
    },
    plugins: [
        react(),
        densifyCloudPlugin({
            backendUrl: BACKEND_DEV_URL,
            sampleTargetText: process.env.VITE_CLOUD_DENSIFY,
            moduleTargetText: process.env.VITE_CLOUD_DENSIFY_MODULES,
        }),
    ],
    build: {
        outDir: "../build/frontend",
        emptyOutDir: true,
    },
    server: {
        proxy: {
            "/api": BACKEND_DEV_URL,
        },
    },
    test: {
        environment: "jsdom",
        // Node 25's own `localStorage` global shadows jsdom's Storage, which the tests exercise.
        poolOptions: { forks: { execArgv: ["--no-experimental-webstorage"] } },
        setupFiles: ["tests/setup.ts"],
        include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
        clearMocks: true,
    },
});
