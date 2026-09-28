import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { describe, expect, it } from "vitest";

import { projectVersion } from "../dev/buildVersion";
import { BUILD_VERSION } from "../src/version";

describe("BUILD_VERSION", () => {
    it("is the version pyproject.toml gives the project, then a commit and a minute", () => {
        // The tests run from the frontend folder, beside which the project file sits.
        const version = projectVersion(pathToFileURL(resolve(process.cwd(), "..", "pyproject.toml")));

        expect(BUILD_VERSION.startsWith(`${version}.`)).toBe(true);
        expect(BUILD_VERSION.slice(version.length + 1)).toMatch(/^[0-9a-f]{7}\.\d{12}$/);
    });
});
