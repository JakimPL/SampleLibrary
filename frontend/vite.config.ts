import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const BACKEND_DEV_URL = process.env.VITE_BACKEND_DEV_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
    plugins: [react()],
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
