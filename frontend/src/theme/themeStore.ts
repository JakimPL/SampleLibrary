import { create } from "zustand";

import type { ThemePreference } from "./themeOptions";
import { readSavedThemePreference, saveThemePreference } from "./themePersistence";

interface ThemeState {
    readonly preference: ThemePreference;
}

interface ThemeActions {
    readonly setPreference: (preference: ThemePreference) => void;
}

function applyThemePreference(preference: ThemePreference): void {
    if (preference === "system") {
        delete document.documentElement.dataset.theme;
    } else {
        document.documentElement.dataset.theme = preference;
    }
}

const initialPreference = readSavedThemePreference();
applyThemePreference(initialPreference);

/**
 * The shell's current theme preference, including "OpenMPT". `setPreference` both applies the
 * choice to `document.documentElement`'s `data-theme` attribute (deleting it for `"system"`, which
 * hands control back to the `prefers-color-scheme` CSS already in `styles.css`) and persists it.
 * The persisted preference is also applied once here, at module load, so the shell's first render
 * never flashes a theme other than the one the user last chose.
 */
export const useThemeStore = create<ThemeState & ThemeActions>((set) => ({
    preference: initialPreference,
    setPreference: (preference) => {
        applyThemePreference(preference);
        saveThemePreference(preference);
        set({ preference });
    },
}));
