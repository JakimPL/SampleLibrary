import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";

const PROJECT_VERSION_PATTERN = /^version = "([^"]+)"$/m;
const COMMIT_LENGTH = 7;
const STAMP_LENGTH = "YYYY-MM-DDTHH:MM".length;

/** The version pyproject.toml gives the project. */
export function projectVersion(projectFile: URL): string {
    const match = PROJECT_VERSION_PATTERN.exec(readFileSync(projectFile, "utf8"));
    if (match?.[1] === undefined) {
        throw new Error("pyproject.toml names no version");
    }
    return match[1];
}

/**
 * The commit a build is made from, shortened to seven characters as git shortens it. A named commit
 * comes first, which is how the site's image learns the commit it is built from; a checkout's own
 * HEAD serves every other build.
 */
export function buildCommit(namedCommit: string | undefined, checkout: URL): string {
    const commit =
        namedCommit !== undefined && namedCommit !== ""
            ? namedCommit
            : execFileSync("git", ["rev-parse", "HEAD"], { cwd: checkout, encoding: "utf8" }).trim();
    return commit.slice(0, COMMIT_LENGTH);
}

/** The minute a build is made, in UTC, as 202609281825. */
export function buildStamp(time: Date): string {
    return time.toISOString().slice(0, STAMP_LENGTH).replace(/[-T:]/g, "");
}

/**
 * What a build of the web app calls itself: the project's version, the commit and the minute, as
 * 0.1.1.abcdef0.202609281825. The commit is looked up in the checkout the project file sits in.
 */
export function buildVersion(projectFile: URL, namedCommit: string | undefined, time: Date): string {
    const checkout = new URL(".", projectFile);
    return [projectVersion(projectFile), buildCommit(namedCommit, checkout), buildStamp(time)].join(".");
}
