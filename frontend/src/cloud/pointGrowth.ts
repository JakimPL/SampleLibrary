import type { PointScaleMode } from "./cloudRenderSettings";

/**
 * How much larger than its base size a point draws at `zoom`, the camera's scaling with 1 at the
 * view the points were first drawn at: the rule regl-scatterplot follows for its own points, so
 * dots drawn in its place grow as they would have.
 */
export function pointGrowth(mode: PointScaleMode, zoom: number): number {
    const magnified = Math.max(1, zoom);
    switch (mode) {
        case "asinh":
            return Math.asinh(magnified) / Math.asinh(1);
        case "linear":
            return magnified;
        case "constant":
            return 1;
    }
}
