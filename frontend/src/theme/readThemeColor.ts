/**
 * Reads a CSS custom property's current resolved value off the document root, for the canvas- and
 * WebGL-backed visuals that cannot consume a `var()` reference the way a styled element does.
 * Falls back to `fallback` when the property resolves empty, e.g. under jsdom in tests.
 */
export function readThemeColor(propertyName: string, fallback: string): string {
    const value = getComputedStyle(document.documentElement).getPropertyValue(propertyName).trim();
    return value === "" ? fallback : value;
}
