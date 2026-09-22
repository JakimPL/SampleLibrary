import type { CloudEntityPoint } from "../geometry";
import type { ScreenPoint } from "../linkGeometry";
import { toData, type ViewTransform } from "../viewTransform";

const COORDINATES_PER_POINT = 2;

/** Every point's x and y in the order the points are indexed, which is the order a hit reports. */
export function flatPositionsOf(points: readonly CloudEntityPoint[]): Float32Array {
    const positions = new Float32Array(points.length * COORDINATES_PER_POINT);
    points.forEach((point, index) => {
        positions[index * COORDINATES_PER_POINT] = point.x;
        positions[index * COORDINATES_PER_POINT + 1] = point.y;
    });
    return positions;
}

/**
 * The index of the point nearest to `screen` within `radiusPx`, or `null` when none stands that
 * close. The search first boxes the radius in the data space, so a pass over a whole catalog
 * only measures the points that could be near.
 */
export function nearestPointIndex(
    positions: Float32Array,
    transform: ViewTransform,
    screen: ScreenPoint,
    radiusPx: number,
): number | null {
    const [centerX, centerY] = toData(transform, screen);
    const [edgeX, edgeY] = toData(transform, [screen[0] + radiusPx, screen[1] + radiusPx]);
    const reachX = Math.abs(edgeX - centerX);
    const reachY = Math.abs(edgeY - centerY);
    const radiusSquared = radiusPx * radiusPx;
    let nearest: number | null = null;
    let nearestDistanceSquared = Number.POSITIVE_INFINITY;
    for (let offset = 0; offset + 1 < positions.length; offset += COORDINATES_PER_POINT) {
        const x = positions[offset] ?? Number.NaN;
        const y = positions[offset + 1] ?? Number.NaN;
        if (Math.abs(x - centerX) > reachX || Math.abs(y - centerY) > reachY) {
            continue;
        }
        const screenX = transform.xx * x + transform.xy * y + transform.offsetX - screen[0];
        const screenY = transform.yx * x + transform.yy * y + transform.offsetY - screen[1];
        const distanceSquared = screenX * screenX + screenY * screenY;
        if (distanceSquared <= radiusSquared && distanceSquared < nearestDistanceSquared) {
            nearestDistanceSquared = distanceSquared;
            nearest = offset / COORDINATES_PER_POINT;
        }
    }
    return nearest;
}
