import type { ChangeEvent, ReactElement } from "react";

import { isThemePreference, THEME_OPTIONS } from "./themeOptions";
import { useThemeStore } from "./themeStore";

/** Top bar control for switching the shell's visual theme, beside the View menu. */
export function ThemeMenu(): ReactElement {
    const preference = useThemeStore((state) => state.preference);
    const setPreference = useThemeStore((state) => state.setPreference);

    function handleChange(event: ChangeEvent<HTMLSelectElement>): void {
        const { value } = event.target;
        if (isThemePreference(value)) {
            setPreference(value);
        }
    }

    return (
        <select className="theme-menu" aria-label="Theme" value={preference} onChange={handleChange}>
            {THEME_OPTIONS.map((option) => (
                <option key={option.id} value={option.id}>
                    {option.label}
                </option>
            ))}
        </select>
    );
}
