import { DEFAULT_THEME_PREFERENCE, isThemePreference, type ThemePreference } from "./themeOptions";

export const THEME_STORAGE_KEY = "samplelibrary-theme-preference";

export function readSavedThemePreference(): ThemePreference {
    try {
        const raw = localStorage.getItem(THEME_STORAGE_KEY);
        return raw !== null && isThemePreference(raw) ? raw : DEFAULT_THEME_PREFERENCE;
    } catch {
        return DEFAULT_THEME_PREFERENCE;
    }
}

export function saveThemePreference(preference: ThemePreference): void {
    try {
        localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
        // localStorage throws in private browsing or on a full quota; the preference then lasts for this session.
    }
}
