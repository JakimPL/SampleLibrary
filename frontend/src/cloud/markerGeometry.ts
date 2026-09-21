import type { MarkerStyle, PointShape } from "./cloudRenderSettings";
import { insetSegment, type ScreenPoint } from "./linkGeometry";

const HALF = 0.5;
const SQUARE_SHAPE = "square";

/** Everything a marker needs to draw itself: the theme's marker style, its point shape, and the display's pixel density. */
export interface MarkerAppearance extends MarkerStyle {
    readonly shape: PointShape;
    readonly devicePixelRatio: number;
}

/** A square's stroke path in CSS pixels: its top-left corner, its side and the stroke's width. */
export interface SquareFrame {
    readonly x: number;
    readonly y: number;
    readonly side: number;
    readonly strokeWidth: number;
}

/** A ring's stroke path in CSS pixels: its radius and the stroke's width. */
export interface RingFrame {
    readonly radius: number;
    readonly strokeWidth: number;
}

/** A CSS length in whole device pixels, one at least. */
export function devicePixels(lengthPx: number, devicePixelRatio: number): number {
    return Math.max(1, Math.round(lengthPx * devicePixelRatio));
}

/** A CSS coordinate moved onto the nearest device pixel boundary. */
export function snapToDevicePixel(coordinatePx: number, devicePixelRatio: number): number {
    return Math.round(coordinatePx * devicePixelRatio) / devicePixelRatio;
}

/**
 * A hollow square of `sizePx` around `center` whose outer edges and stroke fall on whole device
 * pixels, in CSS pixels. Both the side and the stroke round to device pixels, and the corner snaps
 * to the device grid, so a one-pixel frame stays one crisp pixel wide at any pixel density -- the
 * way OpenMPT frames its envelope nodes. The path runs half a stroke inside the outer edge, since
 * a stroke straddles its path.
 */
export function crispSquare(
    center: ScreenPoint,
    sizePx: number,
    lineWidthPx: number,
    devicePixelRatio: number,
): SquareFrame {
    const side = devicePixels(sizePx, devicePixelRatio);
    const line = devicePixels(lineWidthPx, devicePixelRatio);
    const left = Math.round(center[0] * devicePixelRatio - side * HALF);
    const top = Math.round(center[1] * devicePixelRatio - side * HALF);
    return {
        x: (left + line * HALF) / devicePixelRatio,
        y: (top + line * HALF) / devicePixelRatio,
        side: (side - line) / devicePixelRatio,
        strokeWidth: line / devicePixelRatio,
    };
}

/**
 * How far from its center a marker's outer edge lies in the direction of `(towardX, towardY)`: a
 * ring's radius, or the distance to a square's side along that direction, which grows toward the
 * corners.
 */
export function markerReach(appearance: MarkerAppearance, towardX: number, towardY: number): number {
    const halfSize = appearance.sizePx * HALF;
    const length = Math.hypot(towardX, towardY);
    if (appearance.shape !== SQUARE_SHAPE || length === 0) {
        return halfSize;
    }
    return (halfSize * length) / Math.max(Math.abs(towardX), Math.abs(towardY));
}

/**
 * The stretch of the line from `first` to `second` that lies outside the markers on it: the one at
 * `first` always, and the one at `second` when `secondMarked`; null when the markers cover it all.
 */
export function lineBetweenMarkers(
    first: ScreenPoint,
    second: ScreenPoint,
    appearance: MarkerAppearance,
    secondMarked: boolean,
): readonly [ScreenPoint, ScreenPoint] | null {
    const reach = markerReach(appearance, second[0] - first[0], second[1] - first[1]);
    return insetSegment(first, second, reach, secondMarked ? reach : 0);
}

/** A ring whose outer edge spans `sizePx`, the stroke running just inside it. */
export function ringFrame(sizePx: number, lineWidthPx: number): RingFrame {
    return { radius: Math.max(0, (sizePx - lineWidthPx) * HALF), strokeWidth: lineWidthPx };
}
