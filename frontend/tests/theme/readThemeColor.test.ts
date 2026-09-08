import { afterEach, describe, expect, it } from "vitest";

import { readThemeColor } from "../../src/theme/readThemeColor";

const PROPERTY_NAME = "--test-theme-color";

afterEach(() => {
    document.documentElement.style.removeProperty(PROPERTY_NAME);
});

describe("readThemeColor", () => {
    it("returns the fallback when the custom property is not set", () => {
        expect(readThemeColor(PROPERTY_NAME, "#123456")).toBe("#123456");
    });

    it("returns the resolved custom property value when it is set", () => {
        document.documentElement.style.setProperty(PROPERTY_NAME, "#abcdef");

        expect(readThemeColor(PROPERTY_NAME, "#123456")).toBe("#abcdef");
    });

    it("trims whitespace around the resolved value", () => {
        document.documentElement.style.setProperty(PROPERTY_NAME, "  #abcdef  ");

        expect(readThemeColor(PROPERTY_NAME, "#123456")).toBe("#abcdef");
    });
});
