import { readThemeColor } from "../theme/readThemeColor";

const MINI_WAVEFORM_COLOR_PROPERTY = "--mini-waveform-color";
const MINI_WAVEFORM_COLOR_FALLBACK = "#8890a0";

/**
 * The color every compact waveform preview (a sample row's thumbnail, the cloud hover tooltip's
 * preview) draws its bars in. Read explicitly rather than through the canvas's own `currentColor`
 * fill, which this Chromium build resolves to black regardless of the element's actual computed
 * color -- shared by both call sites so the fix and the token name live in exactly one place.
 */
export function readMiniWaveformColor(): string {
    return readThemeColor(MINI_WAVEFORM_COLOR_PROPERTY, MINI_WAVEFORM_COLOR_FALLBACK);
}
