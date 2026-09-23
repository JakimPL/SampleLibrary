import type { EntityRef } from "../workspace/selectionStore";

export interface CloudEntityPoint {
    readonly ref: EntityRef;
    readonly x: number;
    readonly y: number;
    /** The rate a clicked sample point plays at; absent on a module point and on a sample of unknown rate. */
    readonly playbackRateHz?: number;
}

const FALLBACK_RANGE = 1;
const BULK_QUANTILE = 0.01;
const HALF = 0.5;

export interface Bounds {
    readonly minimum: number;
    readonly maximum: number;
}

/** How far one coordinate of a set of points reaches, read in a single pass over them.
 *
 * The pass is what makes this hold a whole catalog: `Math.min(...values)` hands every value over as
 * its own argument, and a hundred thousand of them is past what a call frame takes -- which a
 * browser reports as an exceeded call stack, taking the whole page down with it.
 */
export function boundsOf<Point>(points: readonly Point[], coordinateOf: (point: Point) => number): Bounds {
    let minimum = Number.POSITIVE_INFINITY;
    let maximum = Number.NEGATIVE_INFINITY;
    for (const point of points) {
        const coordinate = coordinateOf(point);
        minimum = Math.min(minimum, coordinate);
        maximum = Math.max(maximum, coordinate);
    }

    return { minimum, maximum };
}

/** Where one coordinate of a set of points is centered and how far it reaches from that center. */
interface AxisFrame {
    readonly center: number;
    readonly halfExtent: number;
}

/**
 * Frames one coordinate on its bulk: centered midway between the `BULK_QUANTILE` and
 * 1 - `BULK_QUANTILE` quantiles, and reaching the point farthest from that center on either side.
 * A few far-flung points then sit at the edge of the view while the bulk of the cloud stays in its middle.
 */
function axisFrameOf(
    points: readonly CloudEntityPoint[],
    coordinateOf: (point: CloudEntityPoint) => number,
): AxisFrame {
    const sorted = Float64Array.from(points, coordinateOf).sort();
    const last = sorted.length - 1;
    const low = sorted[Math.floor(BULK_QUANTILE * last)] ?? 0;
    const high = sorted[Math.ceil((1 - BULK_QUANTILE) * last)] ?? 0;
    const center = (low + high) * HALF;
    const halfExtent = Math.max(center - (sorted[0] ?? 0), (sorted[last] ?? 0) - center);
    return { center, halfExtent: halfExtent || FALLBACK_RANGE };
}

/**
 * Maps a set of points onto regl-scatterplot's own [-1, 1] coordinate space, each axis centered on
 * the bulk of the points.
 *
 * A shared coordinate range across every render keeps the plot centered and fully visible
 * regardless of the arbitrary scale a UMAP fit happens to produce, and centering on the bulk keeps
 * a few distant islands from pushing the main cloud toward one side of the opening view.
 */
export function normalizePoints(points: readonly CloudEntityPoint[]): readonly CloudEntityPoint[] {
    if (points.length === 0) {
        return [];
    }

    const horizontal = axisFrameOf(points, (point) => point.x);
    const vertical = axisFrameOf(points, (point) => point.y);

    return points.map((point) => ({
        ref: point.ref,
        x: (point.x - horizontal.center) / horizontal.halfExtent,
        y: (point.y - vertical.center) / vertical.halfExtent,
        // exactOptionalPropertyTypes requires an absent optional field to be omitted.
        ...(point.playbackRateHz !== undefined && { playbackRateHz: point.playbackRateHz }),
    }));
}
