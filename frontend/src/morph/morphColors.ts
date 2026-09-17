import { colorWithAlpha, mixColors, parseCssColor, type Rgba } from "../theme/cssColor";
import { readThemeColor } from "../theme/readThemeColor";

const FIRST_COLOR_PROPERTY = "--wave-first";
const FIRST_COLOR_FALLBACK = "#2f6f9f";
const SECOND_COLOR_PROPERTY = "--wave-second";
const SECOND_COLOR_FALLBACK = "#c0622a";
const OPAQUE_BLACK: Rgba = [0, 0, 0, 1];
// The ends are outlined faintly enough to read as the ground the render stands on.
const END_ALPHA = 0.3;

/** The colors a morph and its two ends wear: one for each end, and the blend of both for the render standing between them. */
export interface MorphColors {
    readonly first: string;
    readonly second: string;
    readonly between: string;
}

/**
 * The colors a morph is drawn in at one weight, read from the theme each time so a change of theme
 * repaints them.
 *
 * The render wears the blend of both ends at the weight it stands, at full strength, so the
 * contour says where along the path it lies before a note of it sounds. At either end of the path
 * that blend is the end's own color, which is the same thing the renderer does with the audio
 * there. The ends themselves are drawn faintly, standing as the ground the render is read against.
 */
export function readMorphColors(weight: number): MorphColors {
    const first = parseCssColor(readThemeColor(FIRST_COLOR_PROPERTY, FIRST_COLOR_FALLBACK)) ?? OPAQUE_BLACK;
    const second = parseCssColor(readThemeColor(SECOND_COLOR_PROPERTY, SECOND_COLOR_FALLBACK)) ?? OPAQUE_BLACK;
    return {
        first: colorWithAlpha(first, END_ALPHA),
        second: colorWithAlpha(second, END_ALPHA),
        between: mixColors(first, second, weight),
    };
}
