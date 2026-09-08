export type ThemePreference = "system" | "light" | "dark" | "openmpt";

export interface ThemeOption {
    readonly id: ThemePreference;
    readonly label: string;
}

/**
 * Every theme preference the picker offers, in display order. "System" defers to the operating
 * system's own light/dark preference instead of setting `data-theme` on the document at all.
 */
export const THEME_OPTIONS: readonly ThemeOption[] = [
    { id: "system", label: "System" },
    { id: "light", label: "Light" },
    { id: "dark", label: "Dark" },
    { id: "openmpt", label: "OpenMPT" },
];

export const DEFAULT_THEME_PREFERENCE: ThemePreference = "system";

export function isThemePreference(value: string): value is ThemePreference {
    return THEME_OPTIONS.some((option) => option.id === value);
}
