import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

const BACKEND_DEV_URL = "http://127.0.0.1:8000";

export default defineConfig({
    plugins: [react()],
    server: {
        proxy: {
            "/modules": BACKEND_DEV_URL,
            "/samples": BACKEND_DEV_URL,
            "/stats": BACKEND_DEV_URL,
            "/cloud": BACKEND_DEV_URL,
        },
    },
    test: {
        environment: "jsdom",
        setupFiles: ["tests/setup.ts"],
        include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
        clearMocks: true,
    },
});
