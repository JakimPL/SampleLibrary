/**
 * Reads a CSS custom property that holds a plain number off the document root, for a visual that
 * derives its colors rather than reading them ready-made. Falls back to `fallback` when the
 * property resolves empty or to something other than a number, e.g. under jsdom in tests.
 */
export function readThemeNumber(propertyName: string, fallback: number): number {
    const value = Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue(propertyName));
    return Number.isFinite(value) ? value : fallback;
}
