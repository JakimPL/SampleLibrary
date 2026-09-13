import { describe, expect, it } from "vitest";

import { formatPath, holdsTag, withTag } from "../../src/samples/labelText";

describe("formatPath", () => {
    it("writes a path the way a person does, one space after each colon", () => {
        expect(formatPath(["HI-HAT", "CLOSED"])).toBe("HI-HAT: CLOSED");
    });
});

describe("holdsTag", () => {
    it("finds a tag wherever and however it was written", () => {
        expect(holdsTag("snare, hi-hat :closed", "HI-HAT: CLOSED")).toBe(true);
    });

    it("tells a category apart from a specification under it", () => {
        expect(holdsTag("HI-HAT", "HI-HAT: CLOSED")).toBe(false);
        expect(holdsTag(null, "SNARE")).toBe(false);
    });
});

describe("withTag", () => {
    it("starts a label from the tag when there is none", () => {
        expect(withTag(null, "BASS DRUM")).toBe("BASS DRUM");
        expect(withTag("  ", "BASS DRUM")).toBe("BASS DRUM");
    });

    it("appends the tag after what the label already says", () => {
        expect(withTag("SNARE", "LO-FI")).toBe("SNARE, LO-FI");
    });

    it("leaves a label that already holds the tag as it was", () => {
        expect(withTag("snare, lo-fi", "LO-FI")).toBe("snare, lo-fi");
    });
});
