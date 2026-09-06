import { describe, expect, it } from "vitest";

import { THEME_STORAGE_KEY } from "../../src/theme/themePersistence";
import { useThemeStore } from "../../src/theme/themeStore";

describe("themeStore", () => {
    it("starts with the system preference and no explicit data-theme attribute", () => {
        expect(useThemeStore.getState().preference).toBe("system");
        expect(document.documentElement.dataset.theme).toBeUndefined();
    });

    it("applies an explicit preference to the document's data-theme attribute", () => {
        useThemeStore.getState().setPreference("openmpt");

        expect(useThemeStore.getState().preference).toBe("openmpt");
        expect(document.documentElement.dataset.theme).toBe("openmpt");
    });

    it("removes the data-theme attribute for the system preference, deferring to prefers-color-scheme", () => {
        useThemeStore.getState().setPreference("dark");

        useThemeStore.getState().setPreference("system");

        expect(document.documentElement.dataset.theme).toBeUndefined();
    });

    it("persists the chosen preference", () => {
        useThemeStore.getState().setPreference("openmpt");

        expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("openmpt");
    });
});
