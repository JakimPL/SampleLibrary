import { describe, expect, it } from "vitest";

import { flatPositionsOf, nearestPointIndex } from "../../../src/cloud/touch/hitTest";
import { viewTransformOf } from "../../../src/cloud/viewTransform";

const IDENTITY = new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);
const TRANSFORM = viewTransformOf(IDENTITY, { widthPx: 600, heightPx: 600, devicePixelRatio: 1 });
const RADIUS_PX = 22;

describe("flatPositionsOf", () => {
    it("lays every point's x and y out in index order", () => {
        const positions = flatPositionsOf([
            { ref: { kind: "sample", hash: "a" }, x: -1, y: 1 },
            { ref: { kind: "sample", hash: "b" }, x: 0.5, y: -0.25 },
        ]);

        expect(Array.from(positions)).toEqual([-1, 1, 0.5, -0.25]);
    });
});

describe("nearestPointIndex", () => {
    const positions = new Float32Array([-1, -1, 1, 1, 0, 0]);

    it("finds the point within reach of the screen position", () => {
        expect(nearestPointIndex(positions, TRANSFORM, [5, 595], RADIUS_PX)).toBe(0);
        expect(nearestPointIndex(positions, TRANSFORM, [590, 12], RADIUS_PX)).toBe(1);
        expect(nearestPointIndex(positions, TRANSFORM, [300, 300], RADIUS_PX)).toBe(2);
    });

    it("finds nothing past the reach", () => {
        expect(nearestPointIndex(positions, TRANSFORM, [300, 340], RADIUS_PX)).toBeNull();
        expect(nearestPointIndex(new Float32Array(), TRANSFORM, [300, 300], RADIUS_PX)).toBeNull();
    });

    it("prefers the nearer of two points within reach", () => {
        const close = new Float32Array([0, 0, 0.05, 0]);

        expect(nearestPointIndex(close, TRANSFORM, [312, 300], RADIUS_PX)).toBe(1);
        expect(nearestPointIndex(close, TRANSFORM, [303, 300], RADIUS_PX)).toBe(0);
    });
});
