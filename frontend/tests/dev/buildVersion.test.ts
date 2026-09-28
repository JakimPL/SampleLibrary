import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { pathToFileURL } from "node:url";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { buildCommit, buildStamp, buildVersion, projectVersion } from "../../dev/buildVersion";

// The tests run from the frontend folder, inside the checkout.
const CHECKOUT = pathToFileURL(resolve(process.cwd(), ".."));
const NAMED_COMMIT = "abcdef0123456789abcdef0123456789abcdef01";
const BUILD_TIME = new Date(Date.UTC(2026, 8, 28, 18, 25, 59));

let projectDirectory: string;

function writeProjectFile(content: string): URL {
    const projectFile = join(projectDirectory, "pyproject.toml");
    writeFileSync(projectFile, content);
    return pathToFileURL(projectFile);
}

beforeEach(() => {
    projectDirectory = mkdtempSync(join(tmpdir(), "build-version-"));
});

afterEach(() => {
    rmSync(projectDirectory, { recursive: true, force: true });
});

describe("projectVersion", () => {
    it("reads the version the project file gives", () => {
        const projectFile = writeProjectFile('[project]\nname = "demo"\nversion = "2.3.4"\n');

        expect(projectVersion(projectFile)).toBe("2.3.4");
    });

    it("refuses a project file that names no version", () => {
        const projectFile = writeProjectFile('[project]\nname = "demo"\n');

        expect(() => projectVersion(projectFile)).toThrow("names no version");
    });
});

describe("buildCommit", () => {
    it("shortens a named commit to seven characters", () => {
        expect(buildCommit(NAMED_COMMIT, CHECKOUT)).toBe("abcdef0");
    });

    it.each([undefined, ""])("reads the checkout's own commit when %j is named", (namedCommit) => {
        expect(buildCommit(namedCommit, CHECKOUT)).toMatch(/^[0-9a-f]{7}$/);
    });
});

describe("buildStamp", () => {
    it.each([
        { time: BUILD_TIME, stamp: "202609281825" },
        { time: new Date(Date.UTC(2027, 0, 2, 3, 4)), stamp: "202701020304" },
    ])("gives $stamp as the minute in UTC", ({ time, stamp }) => {
        expect(buildStamp(time)).toBe(stamp);
    });
});

describe("buildVersion", () => {
    it("joins the project's version, the commit and the minute", () => {
        const projectFile = writeProjectFile('[project]\nversion = "2.3.4"\n');

        expect(buildVersion(projectFile, NAMED_COMMIT, BUILD_TIME)).toBe("2.3.4.abcdef0.202609281825");
    });
});
