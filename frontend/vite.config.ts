import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Overridable so a dev server can point at a second backend instance (e.g. one serving
// dev-library/config.toml) without disturbing the default that talks to the real one.
const BACKEND_DEV_URL = process.env.VITE_BACKEND_DEV_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
    plugins: [react()],
    server: {
        // Only the API's own prefix is forwarded, so `/samples/{hash}` and `/modules/{hash}`
        // reach the single-page application and survive a reload as the client routes they are.
        proxy: {
            "/api": BACKEND_DEV_URL,
        },
    },
    test: {
        environment: "jsdom",
        // Node's own Web Storage API defines a `localStorage` global that jsdom then leaves in
        // place, and it carries no `clear`, which every test's cleanup calls. Turning it off in
        // the worker processes lets jsdom's own implementation be the one the suite reaches.
        poolOptions: { forks: { execArgv: ["--no-experimental-webstorage"] } },
        setupFiles: ["tests/setup.ts"],
        include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
        clearMocks: true,
    },
});
