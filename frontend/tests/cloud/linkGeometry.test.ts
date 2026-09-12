import { describe, expect, it } from "vitest";

import { pointAlong, projectWeight } from "../../src/cloud/linkGeometry";

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
