import type { Viewport } from "../viewTransform";

/**
 * The scatterplot's camera as this code drives it: a pan in the camera's own normalized space, and
 * a scale about a point of that space. regl-scatterplot hands the camera out untyped, so `cameraOf`
 * probes the two methods before anything trusts it.
 */
export interface CloudCamera {
    readonly pan: (delta: readonly [number, number]) => void;
    readonly scale: (factor: readonly [number, number], center: readonly [number, number]) => void;
}

const NDC_SPAN = 2;

function isCamera(candidate: unknown): candidate is CloudCamera {
    if (typeof candidate !== "object" || candidate === null) {
        return false;
    }
    const record = candidate as Record<string, unknown>;
    return typeof record.pan === "function" && typeof record.scale === "function";
}

/** The camera behind `candidate`, or `null` when the library handed out something else. */
export function cameraOf(candidate: unknown): CloudCamera | null {
    return isCamera(candidate) ? candidate : null;
}

/**
 * Moves the view by a screen distance: a finger dragging `dxPx` right and `dyPx` down carries the
 * points with it. One normalized unit spans half the surface's height on both axes, the way the
 * scatterplot projects its camera, and the camera's vertical axis points up the screen.
 */
export function panBy(camera: CloudCamera, viewport: Viewport, dxPx: number, dyPx: number): void {
    camera.pan([(NDC_SPAN * dxPx) / viewport.heightPx, (-NDC_SPAN * dyPx) / viewport.heightPx]);
}

/**
 * Scales the view by `factor` about the screen point (`xPx`, `yPx`), which stays under the finger:
 * a factor above one zooms in. The center is named in the camera's space, where the horizontal
 * axis is stretched by the surface's aspect ratio.
 */
export function zoomAbout(camera: CloudCamera, viewport: Viewport, factor: number, xPx: number, yPx: number): void {
    const aspectRatio = viewport.widthPx / viewport.heightPx;
    camera.scale(
        [factor, factor],
        [(-1 + (NDC_SPAN * xPx) / viewport.widthPx) * aspectRatio, 1 - (NDC_SPAN * yPx) / viewport.heightPx],
    );
}
