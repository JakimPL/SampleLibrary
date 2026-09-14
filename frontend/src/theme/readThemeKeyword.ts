/**
 * Reads a CSS custom property holding one keyword off the document root, for a canvas- or
 * WebGL-backed visual whose shape or mode a theme picks. Falls back to `fallback` when the property
 * resolves empty or to a keyword outside `keywords`, e.g. under jsdom in tests.
 */
export function readThemeKeyword<Keyword extends string>(
    propertyName: string,
    keywords: readonly Keyword[],
    fallback: Keyword,
): Keyword {
    const value = getComputedStyle(document.documentElement).getPropertyValue(propertyName).trim();
    return keywords.find((keyword) => keyword === value) ?? fallback;
}
