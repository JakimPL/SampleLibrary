/** A color's red, green, blue and alpha channels, each in [0, 1]. */
export type Rgba = readonly [number, number, number, number];

const HEX_PATTERN = /^#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})$/i;
const FUNCTIONAL_PATTERN =
    /^rgba?\(\s*([\d.]+%?)\s*[\s,]\s*([\d.]+%?)\s*[\s,]\s*([\d.]+%?)\s*(?:[,/]\s*([\d.]+%?)\s*)?\)$/i;
const HEX_RADIX = 16;
const CHANNEL_MAXIMUM = 255;
const PERCENT_MAXIMUM = 100;
const LONGEST_SHORT_HEX = 4;
const OPAQUE = 1;

/** Each channel of a hex color's digits, the one-digit forms doubling every digit the way CSS reads them. */
function hexChannels(digits: string): number[] {
    const pairs =
        digits.length <= LONGEST_SHORT_HEX
            ? (digits.match(/./g) ?? []).map((digit) => digit + digit)
            : (digits.match(/../g) ?? []);
    return pairs.map((pair) => Number.parseInt(pair, HEX_RADIX) / CHANNEL_MAXIMUM);
}

function functionalChannel(text: string, scale: number): number {
    const value = Number.parseFloat(text);
    return Math.min(1, Math.max(0, text.endsWith("%") ? value / PERCENT_MAXIMUM : value / scale));
}

/**
 * The channels of a color written the ways the stylesheet writes its tokens: `#rgb`, `#rgba`,
 * `#rrggbb`, `#rrggbbaa`, and `rgb()` or `rgba()` with commas or spaces; null for any other text.
 */
export function parseCssColor(text: string): Rgba | null {
    const trimmed = text.trim();
    if (HEX_PATTERN.test(trimmed)) {
        const [red = 0, green = 0, blue = 0, alpha = OPAQUE] = hexChannels(trimmed.slice(1));
        return [red, green, blue, alpha];
    }
    const functional = FUNCTIONAL_PATTERN.exec(trimmed);
    if (functional === null) {
        return null;
    }
    const [, red = "0", green = "0", blue = "0", alpha] = functional;
    return [
        functionalChannel(red, CHANNEL_MAXIMUM),
        functionalChannel(green, CHANNEL_MAXIMUM),
        functionalChannel(blue, CHANNEL_MAXIMUM),
        alpha === undefined ? OPAQUE : functionalChannel(alpha, OPAQUE),
    ];
}
