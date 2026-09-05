import type { CloudPoint } from "../api/cloud";

export interface Point {
    readonly x: number;
    readonly y: number;
}

export interface NormalizedPoint extends Point {
    readonly sampleHash: string;
}

const FALLBACK_RANGE = 1;

export function normalizePoints(points: readonly CloudPoint[]): readonly NormalizedPoint[] {
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
        sampleHash: point.sample_hash,
        x: (point.x - minX) / rangeX,
        y: (point.y - minY) / rangeY,
    }));
}

export function findNearestPoint(
    points: readonly NormalizedPoint[],
    target: Point,
    maxDistance: number,
): NormalizedPoint | null {
    let nearest: NormalizedPoint | null = null;
    let nearestDistance = Number.POSITIVE_INFINITY;
    for (const point of points) {
        const distance = Math.hypot(point.x - target.x, point.y - target.y);
        if (distance < nearestDistance) {
            nearestDistance = distance;
            nearest = point;
        }
    }

    return nearest !== null && nearestDistance <= maxDistance ? nearest : null;
}
