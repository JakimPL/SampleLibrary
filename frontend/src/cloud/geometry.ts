import type { SampleCategory } from "../samples/category";
import type { EntityRef } from "../workspace/selectionStore";

export interface CloudEntityPoint {
    readonly ref: EntityRef;
    readonly x: number;
    readonly y: number;
    // Present for every sample-cloud point (each sample always resolves to a category, worst case
    // "uncategorized"), and absent for a module-cloud point -- modules carry no category concept.
    readonly category?: SampleCategory;
    // The rate to hear a clicked sample point at. Absent for a module point, and for a sample the
    // catalog knows no rate for.
    readonly playbackRateHz?: number;
}

const NORMALIZED_MIN = -1;
const NORMALIZED_MAX = 1;
const NORMALIZED_SPAN = NORMALIZED_MAX - NORMALIZED_MIN;
const FALLBACK_RANGE = 1;

interface Bounds {
    readonly minimum: number;
    readonly maximum: number;
}

/** How far one coordinate of a set of points reaches, read in a single pass over them.
 *
 * The pass is what makes this hold a whole catalog: `Math.min(...values)` hands every value over as
 * its own argument, and a hundred thousand of them is past what a call frame takes -- which a
 * browser reports as an exceeded call stack, taking the whole page down with it.
 */
function boundsOf(points: readonly CloudEntityPoint[], coordinateOf: (point: CloudEntityPoint) => number): Bounds {
    let minimum = Number.POSITIVE_INFINITY;
    let maximum = Number.NEGATIVE_INFINITY;
    for (const point of points) {
        const coordinate = coordinateOf(point);
        minimum = Math.min(minimum, coordinate);
        maximum = Math.max(maximum, coordinate);
    }

    return { minimum, maximum };
}

/**
 * Maps a set of points' bounding box onto regl-scatterplot's own [-1, 1] coordinate space.
 *
 * A shared coordinate range across every render keeps the plot centered and fully visible
 * regardless of the arbitrary scale a UMAP fit or a placeholder embedding happens to produce.
 */
export function normalizePoints(points: readonly CloudEntityPoint[]): readonly CloudEntityPoint[] {
    if (points.length === 0) {
        return [];
    }

    const horizontal = boundsOf(points, (point) => point.x);
    const vertical = boundsOf(points, (point) => point.y);
    const rangeX = horizontal.maximum - horizontal.minimum || FALLBACK_RANGE;
    const rangeY = vertical.maximum - vertical.minimum || FALLBACK_RANGE;

    return points.map((point) => ({
        ref: point.ref,
        x: NORMALIZED_MIN + ((point.x - horizontal.minimum) / rangeX) * NORMALIZED_SPAN,
        y: NORMALIZED_MIN + ((point.y - vertical.minimum) / rangeY) * NORMALIZED_SPAN,
        // Spread conditionally rather than assigning `point.category` outright: with
        // exactOptionalPropertyTypes on, an optional field must be omitted, not set to `undefined`.
        ...(point.category !== undefined && { category: point.category }),
        ...(point.playbackRateHz !== undefined && { playbackRateHz: point.playbackRateHz }),
    }));
}
