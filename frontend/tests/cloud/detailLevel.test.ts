import { describe, expect, it } from "vitest";

import { countVisibleUpTo, detailNodeLimit } from "../../src/cloud/detailLevel";
import { viewTransformOf } from "../../src/cloud/viewTransform";

const IDENTITY = new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
const BOUNDS = { minimumX: -1, maximumX: 1, minimumY: -1, maximumY: 1 };

describe("detailNodeLimit", () => {
    it("allows more markers on a larger surface and fewer for larger markers", () => {
        const small = viewTransformOf(IDENTITY, { widthPx: 400, heightPx: 300, devicePixelRatio: 1 });
        const large = viewTransformOf(IDENTITY, { widthPx: 1600, heightPx: 900, devicePixelRatio: 1 });

        expect(detailNodeLimit(large, 7)).toBeGreaterThan(detailNodeLimit(small, 7));
        expect(detailNodeLimit(large, 14)).toBeLessThan(detailNodeLimit(large, 7));
        expect(detailNodeLimit(large, 7) * 7 * 7).toBeLessThan(1600 * 900);
    });
});

describe("countVisibleUpTo", () => {
    it("counts the points within the bounds", () => {
        const positions = new Float32Array([0, 0, 0.5, -0.5, 2, 0, 0, -3, 1, 1]);

        expect(countVisibleUpTo(positions, BOUNDS, 100)).toBe(3);
    });

    it("stops one past the limit", () => {
        const positions = new Float32Array(Array.from({ length: 2000 }, () => 0));

        expect(countVisibleUpTo(positions, BOUNDS, 10)).toBe(11);
    });

    it("counts nothing in an empty batch", () => {
        expect(countVisibleUpTo(new Float32Array(), BOUNDS, 10)).toBe(0);
    });
});
