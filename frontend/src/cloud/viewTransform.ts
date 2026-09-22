import type { ScreenPoint } from "./linkGeometry";

/** The cloud's drawing surface: its size in CSS pixels, and the display's pixel density. */
export interface Viewport {
    readonly widthPx: number;
    readonly heightPx: number;
    readonly devicePixelRatio: number;
}

/**
 * Where the scatterplot's camera puts data coordinates on screen: an affine map from the
 * normalized data space onto CSS pixels measured from the surface's top-left corner.
 */
export interface ViewTransform extends Viewport {
    /** The camera's scaling: 1 at the view the points were first drawn at, larger zoomed in. */
    readonly zoom: number;
    /** The screen position of data (x, y) is `[xx * x + xy * y + offsetX, yx * x + yy * y + offsetY]`. */
    readonly xx: number;
    readonly xy: number;
    readonly yx: number;
    readonly yy: number;
    readonly offsetX: number;
    readonly offsetY: number;
}

/** The part of the data space a transform shows, as a bounding box. */
export interface DataBounds {
    readonly minimumX: number;
    readonly maximumX: number;
    readonly minimumY: number;
    readonly maximumY: number;
}

const HALF = 0.5;
// A column-major 4x4 matrix: the 2D camera's linear part and translation sit at these indices.
const VIEW_XX = 0;
const VIEW_YX = 1;
const VIEW_XY = 4;
const VIEW_YY = 5;
const VIEW_OFFSET_X = 12;
const VIEW_OFFSET_Y = 13;
const IDENTITY_SCALE = 1;
const NO_OFFSET = 0;

function entry(cameraView: Float32Array, index: number, fallback: number): number {
    return cameraView[index] ?? fallback;
}

/**
 * The transform regl-scatterplot applies to its points: the camera view, then its local projection
 * (`1 / aspect` horizontally), then clip space onto the surface. Half the surface's height is the
 * pixel length of one clip unit on both axes, which is how the scatterplot keeps the data square
 * whatever the surface's aspect.
 */
export function viewTransformOf(cameraView: Float32Array, viewport: Viewport): ViewTransform {
    const unit = viewport.heightPx * HALF;
    return {
        ...viewport,
        zoom: entry(cameraView, VIEW_XX, IDENTITY_SCALE),
        xx: entry(cameraView, VIEW_XX, IDENTITY_SCALE) * unit,
        xy: entry(cameraView, VIEW_XY, NO_OFFSET) * unit,
        yx: -entry(cameraView, VIEW_YX, NO_OFFSET) * unit,
        yy: -entry(cameraView, VIEW_YY, IDENTITY_SCALE) * unit,
        offsetX: viewport.widthPx * HALF + entry(cameraView, VIEW_OFFSET_X, NO_OFFSET) * unit,
        offsetY: unit - entry(cameraView, VIEW_OFFSET_Y, NO_OFFSET) * unit,
    };
}

export function toScreen(transform: ViewTransform, x: number, y: number): ScreenPoint {
    return [
        transform.xx * x + transform.xy * y + transform.offsetX,
        transform.yx * x + transform.yy * y + transform.offsetY,
    ];
}

/** The data coordinates a screen point shows, by inverting the transform's linear part. */
export function toData(transform: ViewTransform, screen: ScreenPoint): readonly [number, number] {
    const determinant = transform.xx * transform.yy - transform.xy * transform.yx;
    const shiftedX = screen[0] - transform.offsetX;
    const shiftedY = screen[1] - transform.offsetY;
    return [
        (transform.yy * shiftedX - transform.xy * shiftedY) / determinant,
        (transform.xx * shiftedY - transform.yx * shiftedX) / determinant,
    ];
}

/** The data-space box around everything the surface shows, grown by `marginPx` on every side. */
export function visibleBounds(transform: ViewTransform, marginPx: number): DataBounds {
    const corners = [
        toData(transform, [-marginPx, -marginPx]),
        toData(transform, [transform.widthPx + marginPx, -marginPx]),
        toData(transform, [-marginPx, transform.heightPx + marginPx]),
        toData(transform, [transform.widthPx + marginPx, transform.heightPx + marginPx]),
    ];
    const xs = corners.map((corner) => corner[0]);
    const ys = corners.map((corner) => corner[1]);
    return {
        minimumX: Math.min(...xs),
        maximumX: Math.max(...xs),
        minimumY: Math.min(...ys),
        maximumY: Math.max(...ys),
    };
}

export function sameTransform(first: ViewTransform | null, second: ViewTransform | null): boolean {
    return first === null || second === null
        ? first === second
        : first.xx === second.xx &&
              first.xy === second.xy &&
              first.yx === second.yx &&
              first.yy === second.yy &&
              first.offsetX === second.offsetX &&
              first.offsetY === second.offsetY &&
              first.widthPx === second.widthPx &&
              first.heightPx === second.heightPx &&
              first.devicePixelRatio === second.devicePixelRatio;
}
