import { describe, expect, it } from "vitest";

import { formatBytes, formatDuration } from "../../src/shared/format";

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
