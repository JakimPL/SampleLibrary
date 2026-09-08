import { describe, expect, it } from "vitest";

import { DEFAULT_THEME_PREFERENCE } from "../../src/theme/themeOptions";
import { readSavedThemePreference, saveThemePreference, THEME_STORAGE_KEY } from "../../src/theme/themePersistence";

describe("themePersistence", () => {
    it("returns the default preference when nothing has been saved", () => {
        expect(readSavedThemePreference()).toBe(DEFAULT_THEME_PREFERENCE);
    });

    it("round-trips a saved preference", () => {
        saveThemePreference("openmpt");

        expect(readSavedThemePreference()).toBe("openmpt");
    });

    it("falls back to the default preference when the stored value is not a known one", () => {
        localStorage.setItem(THEME_STORAGE_KEY, "sepia");

        expect(readSavedThemePreference()).toBe(DEFAULT_THEME_PREFERENCE);
    });
});
