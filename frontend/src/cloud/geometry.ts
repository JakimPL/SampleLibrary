import type { EntityRef } from "../workspace/selectionStore";

export interface CloudEntityPoint {
    readonly ref: EntityRef;
    readonly x: number;
    readonly y: number;
}

const NORMALIZED_MIN = -1;
const NORMALIZED_MAX = 1;
const NORMALIZED_SPAN = NORMALIZED_MAX - NORMALIZED_MIN;
const FALLBACK_RANGE = 1;

/**
 * Maps a set of points' bounding box onto regl-scatterplot's own [-1, 1] coordinate space.
 *
 * A shared coordinate range across every render keeps the plot centred and fully visible
 * regardless of the arbitrary scale a UMAP fit or a placeholder embedding happens to produce.
 */
export function normalizePoints(points: readonly CloudEntityPoint[]): readonly CloudEntityPoint[] {
    if (points.length === 0) {
        return [];
    }

    const xValues = points.map((point) => point.x);
    const yValues = points.map((point) => point.y);
    const minX = Math.min(...xValues);
    const maxX = Math.max(...xValues);
    const minY = Math.min(...yValues);
    const maxY = Math.max(...yValues);
    const rangeX = maxX - minX || FALLBACK_RANGE;
    const rangeY = maxY - minY || FALLBACK_RANGE;

    return points.map((point) => ({
        ref: point.ref,
        x: NORMALIZED_MIN + ((point.x - minX) / rangeX) * NORMALIZED_SPAN,
        y: NORMALIZED_MIN + ((point.y - minY) / rangeY) * NORMALIZED_SPAN,
    }));
}
