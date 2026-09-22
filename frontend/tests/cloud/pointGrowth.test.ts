import { describe, expect, it } from "vitest";

import { pointGrowth } from "../../src/cloud/pointGrowth";

describe("pointGrowth", () => {
    it("holds a point at its base size at the first view, and when zoomed out past it", () => {
        expect(pointGrowth("asinh", 1)).toBeCloseTo(1, 5);
        expect(pointGrowth("asinh", 0.25)).toBeCloseTo(1, 5);
        expect(pointGrowth("linear", 0.5)).toBe(1);
    });

    it("grows a point with the zoom by the theme's rule", () => {
        expect(pointGrowth("asinh", 4)).toBeCloseTo(Math.asinh(4) / Math.asinh(1), 5);
        expect(pointGrowth("linear", 4)).toBe(4);
        expect(pointGrowth("constant", 4)).toBe(1);
    });
});
