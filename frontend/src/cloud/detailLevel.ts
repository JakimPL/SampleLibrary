import type { DataBounds, ViewTransform } from "./viewTransform";

const DETAIL_COVERAGE = 0.3;
const COORDINATES_PER_POINT = 2;

/**
 * How many markers of `nodeSizePx` the detail mode shows at most on the transform's surface: as
 * many as cover under a third of it, past which neighboring markers mostly overlap and the points
 * read better as dots. The count follows the surface's area, so a small panel switches to markers
 * only once a view holds as few points as fit it legibly, and a large one sooner.
 */
export function detailNodeLimit(transform: ViewTransform, nodeSizePx: number): number {
    const nodeArea = Math.max(1, nodeSizePx * nodeSizePx);
    return Math.floor((transform.widthPx * transform.heightPx * DETAIL_COVERAGE) / nodeArea);
}

/**
 * How many of the points in `positions` (x and y pairs) fall within `bounds`, counting no further
 * than one past `limit`: all a caller deciding between "within the limit" and "past it" needs,
 * which spares a zoomed-out view the pass over every point.
 */
export function countVisibleUpTo(positions: Float32Array, bounds: DataBounds, limit: number): number {
    let count = 0;
    for (let offset = 0; offset + 1 < positions.length && count <= limit; offset += COORDINATES_PER_POINT) {
        const x = positions[offset] ?? Number.NaN;
        const y = positions[offset + 1] ?? Number.NaN;
        if (x >= bounds.minimumX && x <= bounds.maximumX && y >= bounds.minimumY && y <= bounds.maximumY) {
            count += 1;
        }
    }
    return count;
}
