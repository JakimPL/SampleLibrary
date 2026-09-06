import { useEffect, useState } from "react";

import type { ThemePreference } from "./themeOptions";
import { useThemeStore } from "./themeStore";

const DARK_MEDIA_QUERY = "(prefers-color-scheme: dark)";

export interface ThemeSignal {
    readonly preference: ThemePreference;
    readonly systemVersion: number;
}

/**
 * Reports everything that can change which theme is actually applied to the page: the explicit
 * preference itself, and -- while it defers to the operating system -- a live OS light/dark flip.
 * `styles.css`'s `prefers-color-scheme` rules pick up that flip on their own, but a canvas- or
 * WebGL-backed visual that reads resolved colors imperatively cannot, so it depends on both fields
 * here to know when to re-read theme colors and re-apply them to its own instance.
 */
export function useThemeSignal(): ThemeSignal {
    const preference = useThemeStore((state) => state.preference);
    const [systemVersion, setSystemVersion] = useState(0);

    useEffect(() => {
        const media = window.matchMedia(DARK_MEDIA_QUERY);
        function handleChange(): void {
            setSystemVersion((version) => version + 1);
        }
        media.addEventListener("change", handleChange);
        return (): void => {
            media.removeEventListener("change", handleChange);
        };
    }, []);

    return { preference, systemVersion };
}
