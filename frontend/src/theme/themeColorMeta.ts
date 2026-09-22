import { useEffect } from "react";

import { useThemeSignal } from "./useThemeSignal";

const THEME_COLOR_META_SELECTOR = 'meta[name="theme-color"]';
/** The token the shell's bars are painted in, which the browser's own chrome then matches. */
const CHROME_COLOR_PROPERTY = "--surface-2";

/** Writes the applied theme's bar color into every theme-color meta, so the browser's chrome matches the shell's. */
export function syncThemeColorMeta(): void {
    const color = getComputedStyle(document.documentElement).getPropertyValue(CHROME_COLOR_PROPERTY).trim();
    if (color === "") {
        return;
    }
    for (const meta of document.head.querySelectorAll<HTMLMetaElement>(THEME_COLOR_META_SELECTOR)) {
        meta.content = color;
    }
}

/** Keeps the browser's chrome in the shell's bar color as the theme preference or the system scheme changes. */
export function useThemeColorMeta(): void {
    const { preference, systemVersion } = useThemeSignal();
    useEffect(() => {
        syncThemeColorMeta();
    }, [preference, systemVersion]);
}
