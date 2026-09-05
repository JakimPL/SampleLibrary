import { describe, expect, it } from "vitest";

import type { CloudPoint } from "../../src/api/cloud";
import { findNearestPoint, normalizePoints } from "../../src/cloud/geometry";

function point(sampleHash: string, x: number, y: number): CloudPoint {
    return { sample_hash: sampleHash, x, y, computed_at: "2026-01-01T00:00:00Z" };
}

describe("normalizePoints", () => {
    it("returns nothing for an empty input", () => {
        expect(normalizePoints([])).toEqual([]);
    });

    it("maps the bounding box of the input onto the unit square", () => {
        const points = [point("a", 0, 0), point("b", 10, 20)];

        const normalized = normalizePoints(points);

        expect(normalized).toEqual([
            { sampleHash: "a", x: 0, y: 0 },
            { sampleHash: "b", x: 1, y: 1 },
        ]);
    });

    it("does not divide by zero when every point shares a coordinate", () => {
        const points = [point("a", 5, 5), point("b", 5, 5)];

        const normalized = normalizePoints(points);

        expect(normalized.every((entry) => Number.isFinite(entry.x) && Number.isFinite(entry.y))).toBe(true);
    });
});

describe("findNearestPoint", () => {
    const points = [
        { sampleHash: "a", x: 0, y: 0 },
        { sampleHash: "b", x: 1, y: 1 },
    ];

    it("finds the closest point within the given radius", () => {
        expect(findNearestPoint(points, { x: 0.05, y: 0.05 }, 0.5)).toEqual(points[0]);
    });

    it("returns null when nothing is within the given radius", () => {
        expect(findNearestPoint(points, { x: 0.5, y: 0.5 }, 0.1)).toBeNull();
    });

    it("returns null for an empty point list", () => {
        expect(findNearestPoint([], { x: 0, y: 0 }, 1)).toBeNull();
    });
});
