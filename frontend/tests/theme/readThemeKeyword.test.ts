import { afterEach, describe, expect, it } from "vitest";

import { readThemeKeyword } from "../../src/theme/readThemeKeyword";

const PROPERTY_NAME = "--test-theme-keyword";
const KEYWORDS = ["circle", "square"] as const;

afterEach(() => {
    document.documentElement.style.removeProperty(PROPERTY_NAME);
});

describe("readThemeKeyword", () => {
    it("returns the fallback when the custom property is not set", () => {
        expect(readThemeKeyword(PROPERTY_NAME, KEYWORDS, "circle")).toBe("circle");
    });

    it("returns the keyword the custom property holds, trimmed", () => {
        document.documentElement.style.setProperty(PROPERTY_NAME, "  square ");

        expect(readThemeKeyword(PROPERTY_NAME, KEYWORDS, "circle")).toBe("square");
    });

    it("returns the fallback for a value outside the allowed keywords", () => {
        document.documentElement.style.setProperty(PROPERTY_NAME, "triangle");

        expect(readThemeKeyword(PROPERTY_NAME, KEYWORDS, "circle")).toBe("circle");
    });
});
