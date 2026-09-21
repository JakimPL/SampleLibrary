import { describe, expect, it } from "vitest";

import { insetSegment, pointAlong, projectWeight } from "../../src/cloud/linkGeometry";

const FIRST = [10, 20] as const;
const SECOND = [110, 20] as const;

describe("pointAlong", () => {
    it("walks from the first end to the second", () => {
        expect(pointAlong(FIRST, SECOND, 0)).toEqual([10, 20]);
        expect(pointAlong(FIRST, SECOND, 0.5)).toEqual([60, 20]);
        expect(pointAlong(FIRST, SECOND, 1)).toEqual([110, 20]);
    });
});

describe("projectWeight", () => {
    it("reads a point beside the line as its position along it", () => {
        expect(projectWeight(FIRST, SECOND, [35, 80])).toBeCloseTo(0.25);
    });

    it("holds a point past either end to that end", () => {
        expect(projectWeight(FIRST, SECOND, [-40, 20])).toBe(0);
        expect(projectWeight(FIRST, SECOND, [500, 20])).toBe(1);
    });

    it("puts every point at the start when the two ends coincide", () => {
        expect(projectWeight(FIRST, FIRST, [60, 20])).toBe(0);
    });
});

describe("insetSegment", () => {
    it("cuts each end by its own inset along the segment", () => {
        expect(insetSegment(FIRST, SECOND, 5, 15)).toEqual([
            [15, 20],
            [95, 20],
        ]);
    });

    it("keeps the direction of a diagonal segment", () => {
        const segment = insetSegment([0, 0], [30, 40], 5, 5);

        expect(segment?.[0][0]).toBeCloseTo(3);
        expect(segment?.[0][1]).toBeCloseTo(4);
        expect(segment?.[1][0]).toBeCloseTo(27);
        expect(segment?.[1][1]).toBeCloseTo(36);
    });

    it("leaves nothing once the cuts meet", () => {
        expect(insetSegment(FIRST, SECOND, 60, 40)).toBeNull();
        expect(insetSegment(FIRST, FIRST, 0, 0)).toBeNull();
    });
});
