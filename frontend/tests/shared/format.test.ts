import { describe, expect, it } from "vitest";

import { fileNameStem, formatBytes, formatDuration, shortHash } from "../../src/shared/format";

describe("formatBytes", () => {
    it("formats zero bytes", () => {
        expect(formatBytes(0)).toBe("0 B");
    });

    it("formats a byte count under the first unit step without a fraction", () => {
        expect(formatBytes(512)).toBe("512 B");
    });

    it("formats exactly one kibibyte", () => {
        expect(formatBytes(1024)).toBe("1.0 KiB");
    });

    it("formats a byte count spanning multiple unit steps", () => {
        expect(formatBytes(1024 * 1024 * 5)).toBe("5.0 MiB");
    });
});

describe("formatDuration", () => {
    it("formats seconds with two decimal places", () => {
        expect(formatDuration(1.5)).toBe("1.50 s");
    });

    it("formats a sub-second duration", () => {
        expect(formatDuration(0.023)).toBe("0.02 s");
    });
});

describe("shortHash", () => {
    it("takes the leading 8 characters of a hash", () => {
        expect(shortHash("a3f9c21b7e4d0102030405060708090a0b0c0d0e0f101112131415161718191a")).toBe("a3f9c21b");
    });

    it("returns the whole value when it is already shorter than the short form", () => {
        expect(shortHash("abc")).toBe("abc");
    });
});

/** One name a thing is saved under: what the catalog calls it, and the stem a file takes. */
interface FileNameCase {
    readonly name: string;
    readonly given: string;
    readonly stem: string;
}

const FILE_NAME_CASES: readonly FileNameCase[] = [
    { name: "keeps a name a file system takes as it reads", given: "crash cymbal 2", stem: "crash cymbal 2" },
    { name: "keeps the dots and dashes a name carries", given: "kick-808.loud", stem: "kick-808.loud" },
    { name: "puts one underscore where a path separator stood", given: "drums/kick", stem: "drums_kick" },
    { name: "puts one underscore where a run of reserved characters stood", given: 'a<>:"|?*b', stem: "a_b" },
    { name: "falls back for a name that is only spacing", given: "   ", stem: "fallback" },
    { name: "falls back for a name the catalog leaves empty", given: "", stem: "fallback" },
];

describe("fileNameStem", () => {
    it.each(FILE_NAME_CASES)("$name", ({ given, stem }: FileNameCase) => {
        expect(fileNameStem(given, "fallback")).toBe(stem);
    });
});
