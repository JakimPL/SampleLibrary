import { readThemeNumber } from "./readThemeNumber";

const LIGHTNESS_PROPERTY = "--label-lightness";
const CHROMA_PROPERTY = "--label-chroma";
const LIGHTNESS_FALLBACK = 0.58;
const CHROMA_FALLBACK = 0.17;
// Successive hues a golden angle apart never repeat and stay as far from one another as a sequence
// of unknown length can, which is what a vocabulary that grows one tag at a time asks for.
const GOLDEN_ANGLE_DEGREES = 137.50776405;
// Where the sequence starts, chosen so its first hues keep clear of the accent the selection ring
// and the highlighted point are drawn in.
const HUE_OFFSET_DEGREES = 200;
const FULL_TURN_DEGREES = 360;
const HALF_TURN_DEGREES = 180;
const HEX_RADIX = 16;
const HEX_DIGITS_PER_CHANNEL = 2;
const CHANNEL_MAXIMUM = 255;
const CUBE = 3;

type Triple = readonly [number, number, number];

interface Coefficients {
    readonly first: number;
    readonly second: number;
    readonly third: number;
}

type Matrix = readonly [Coefficients, Coefficients, Coefficients];

// Björn Ottosson's OKLab: lightness and the two opponent axes map linearly to a cone response
// whose cube is linear light, and that in turn maps linearly to linear sRGB.
const LAB_TO_CONES: Matrix = [
    { first: 1, second: 0.3963377774, third: 0.2158037573 },
    { first: 1, second: -0.1055613458, third: -0.0638541728 },
    { first: 1, second: -0.0894841775, third: -1.291485548 },
];
const CONES_TO_LINEAR_RGB: Matrix = [
    { first: 4.0767416621, second: -3.3077115913, third: 0.2309699292 },
    { first: -1.2684380046, second: 2.6097574011, third: -0.3413193965 },
    { first: -0.0041960863, second: -0.7034186147, third: 1.707614701 },
];

// The sRGB transfer curve: linear near black, a gamma curve above.
const SRGB_LINEAR_LIMIT = 0.0031308;
const SRGB_LINEAR_SLOPE = 12.92;
const SRGB_CURVE_GAIN = 1.055;
const SRGB_CURVE_OFFSET = 0.055;
const SRGB_CURVE_EXPONENT = 2.4;

export interface LabelPaletteParameters {
    /** Perceptual lightness in OKLCH, in `[0, 1]`. */
    readonly lightness: number;
    /** Chroma in OKLCH; around 0.15 keeps every hue inside the sRGB gamut at these lightnesses. */
    readonly chroma: number;
}

/** The lightness and chroma the current theme paints label colors at, so they read alike on either ground. */
export function readLabelPaletteParameters(): LabelPaletteParameters {
    return {
        lightness: readThemeNumber(LIGHTNESS_PROPERTY, LIGHTNESS_FALLBACK),
        chroma: readThemeNumber(CHROMA_PROPERTY, CHROMA_FALLBACK),
    };
}

/** The hue, in degrees, the tag of a given rank is painted in. */
export function labelHue(rank: number): number {
    return (HUE_OFFSET_DEGREES + rank * GOLDEN_ANGLE_DEGREES) % FULL_TURN_DEGREES;
}

/**
 * The color a tag of a given rank is painted in, as a hex triplet.
 *
 * Nothing about any particular tag is known here: a color is a function of the rank the server
 * gives a tag by the order it was first used, so a tag keeps its color as the vocabulary grows and
 * a new tag takes the next hue along. Equal lightness and chroma for every hue keep the tags
 * evenly weighted against one another and against the ground they sit on.
 */
export function labelColor(rank: number, parameters: LabelPaletteParameters): string {
    const hue = (labelHue(rank) * Math.PI) / HALF_TURN_DEGREES;
    const [red, green, blue] = oklabToSrgb([
        parameters.lightness,
        parameters.chroma * Math.cos(hue),
        parameters.chroma * Math.sin(hue),
    ]);
    return `#${hexChannel(red)}${hexChannel(green)}${hexChannel(blue)}`;
}

function apply(matrix: Matrix, vector: Triple): Triple {
    const [x, y, z] = vector;
    const [rowA, rowB, rowC] = matrix;
    const dot = (row: Coefficients): number => row.first * x + row.second * y + row.third * z;
    return [dot(rowA), dot(rowB), dot(rowC)];
}

function oklabToSrgb(lab: Triple): Triple {
    const [longCone, mediumCone, shortCone] = apply(LAB_TO_CONES, lab);
    const [red, green, blue] = apply(CONES_TO_LINEAR_RGB, [longCone ** CUBE, mediumCone ** CUBE, shortCone ** CUBE]);
    return [transfer(red), transfer(green), transfer(blue)];
}

function transfer(linear: number): number {
    const clamped = Math.min(Math.max(linear, 0), 1);
    return clamped <= SRGB_LINEAR_LIMIT
        ? SRGB_LINEAR_SLOPE * clamped
        : SRGB_CURVE_GAIN * clamped ** (1 / SRGB_CURVE_EXPONENT) - SRGB_CURVE_OFFSET;
}

function hexChannel(value: number): string {
    return Math.round(value * CHANNEL_MAXIMUM)
        .toString(HEX_RADIX)
        .padStart(HEX_DIGITS_PER_CHANNEL, "0");
}
