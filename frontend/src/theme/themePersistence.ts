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
        // localStorage can be unavailable (private browsing, a full quota) -- losing the saved
        // preference for this session is an acceptable degradation, not a reason to crash the shell.
    }
}
