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

const SRGB_ENCODED_LINEAR_LIMIT = 0.04045;
const SRGB_LINEAR_LIMIT = 0.0031308;
const SRGB_LINEAR_SLOPE = 12.92;
const SRGB_GAMMA_SCALE = 1.055;
const SRGB_GAMMA_OFFSET = 0.055;
const SRGB_GAMMA_EXPONENT = 2.4;
/** One channel as the light it stands for, which is the quantity a blend of two colors adds up. */
function asLight(channel: number): number {
    if (channel <= SRGB_ENCODED_LINEAR_LIMIT) {
        return channel / SRGB_LINEAR_SLOPE;
    }
    return ((channel + SRGB_GAMMA_OFFSET) / SRGB_GAMMA_SCALE) ** SRGB_GAMMA_EXPONENT;
}

/** Light written back as a channel, the way a display reads one. */
function asChannel(light: number): number {
    if (light <= SRGB_LINEAR_LIMIT) {
        return light * SRGB_LINEAR_SLOPE;
    }
    return SRGB_GAMMA_SCALE * light ** (1 / SRGB_GAMMA_EXPONENT) - SRGB_GAMMA_OFFSET;
}

function between(first: number, second: number, weight: number): number {
    return first * (1 - weight) + second * weight;
}

function mixedChannel(first: number, second: number, weight: number): number {
    return Math.round(CHANNEL_MAXIMUM * asChannel(between(asLight(first), asLight(second), weight)));
}

/**
 * The color `weight` of the way from one to another, as a CSS `rgb()` the stylesheet and a canvas
 * both read.
 *
 * The channels are added up as the light they stand for and written back afterwards, so a point
 * halfway between two colors keeps the brightness of both rather than the dimmer reading a
 * straight average of the encoded channels gives. A weight of 0 returns the first color and a
 * weight of 1 the second, which is what lets a blend drawn over its own two ends land exactly on
 * one of them at either end of the path.
 */
export function mixColors(first: Rgba, second: Rgba, weight: number): string {
    const [firstRed, firstGreen, firstBlue, firstAlpha] = first;
    const [secondRed, secondGreen, secondBlue, secondAlpha] = second;
    const red = mixedChannel(firstRed, secondRed, weight);
    const green = mixedChannel(firstGreen, secondGreen, weight);
    const blue = mixedChannel(firstBlue, secondBlue, weight);
    const alpha = between(firstAlpha, secondAlpha, weight);
    return `rgb(${String(red)} ${String(green)} ${String(blue)} / ${String(alpha)})`;
}
