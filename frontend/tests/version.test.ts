import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { APP_VERSION } from "../src/version";

describe("APP_VERSION", () => {
    it("is the version pyproject.toml gives the project", () => {
        // The tests run from the frontend folder, beside which the project file sits.
        const project = readFileSync(resolve(process.cwd(), "..", "pyproject.toml"), "utf8");

        expect(APP_VERSION).toBe(/^version = "([^"]+)"$/m.exec(project)?.[1]);
    });
});
