import { describe, expect, it } from "vitest";

import { sameTransform, toData, toScreen, viewTransformOf, visibleBounds } from "../../src/cloud/viewTransform";

const IDENTITY = new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]);

/** A 2D camera view as regl-scatterplot keeps it: column-major, scaled by `scale` and moved by `offset`. */
function cameraView(scale: number, offsetX: number, offsetY: number): Float32Array {
    return new Float32Array([scale, 0, 0, 0, 0, scale, 0, 0, 0, 0, 1, 0, offsetX, offsetY, 0, 1]);
}

/** What regl-scatterplot's own `getScreenPosition` computes for a point under a view on a surface. */
function libraryScreenPosition(
    view: Float32Array,
    widthPx: number,
    heightPx: number,
    x: number,
    y: number,
): readonly [number, number] {
    const aspect = widthPx / heightPx;
    const cameraX = (view[0] ?? 1) * x + (view[4] ?? 0) * y + (view[12] ?? 0);
    const cameraY = (view[1] ?? 0) * x + (view[5] ?? 1) * y + (view[13] ?? 0);
    const clipX = cameraX / aspect;
    return [(widthPx * (clipX + 1)) / 2, heightPx * (0.5 - cameraY / 2)];
}

describe("viewTransformOf", () => {
    it("maps the data space onto a square surface under the identity view", () => {
        const transform = viewTransformOf(IDENTITY, { widthPx: 600, heightPx: 600, devicePixelRatio: 1 });

        expect(toScreen(transform, 0, 0)).toEqual([300, 300]);
        expect(toScreen(transform, 1, 1)).toEqual([600, 0]);
        expect(toScreen(transform, -1, -1)).toEqual([0, 600]);
    });

    it.each([
        { name: "a wide surface", view: cameraView(2, 0.3, -0.1), widthPx: 800, heightPx: 600 },
        { name: "a tall surface", view: cameraView(0.5, -0.2, 0.4), widthPx: 300, heightPx: 700 },
        {
            name: "a rotated view",
            view: new Float32Array([0.8, 0.6, 0, 0, -0.6, 0.8, 0, 0, 0, 0, 1, 0, 0.1, 0.2, 0, 1]),
            widthPx: 640,
            heightPx: 480,
        },
    ])("agrees with the scatterplot's own screen positions on $name", ({ view, widthPx, heightPx }) => {
        const transform = viewTransformOf(view, { widthPx, heightPx, devicePixelRatio: 1.75 });

        for (const [x, y] of [
            [0, 0],
            [0.4, -0.7],
            [-1, 1],
        ] as const) {
            const [expectedX, expectedY] = libraryScreenPosition(view, widthPx, heightPx, x, y);
            const [screenX, screenY] = toScreen(transform, x, y);
            expect(screenX).toBeCloseTo(expectedX, 3);
            expect(screenY).toBeCloseTo(expectedY, 3);
        }
    });

    it("finds the data point back from its screen position", () => {
        const transform = viewTransformOf(cameraView(3, 0.5, 0.25), {
            widthPx: 900,
            heightPx: 500,
            devicePixelRatio: 2,
        });

        const [x, y] = toData(transform, toScreen(transform, 0.123, -0.456));

        expect(x).toBeCloseTo(0.123, 6);
        expect(y).toBeCloseTo(-0.456, 6);
    });
});

describe("visibleBounds", () => {
    it("spans the data the surface shows, grown by the margin", () => {
        const transform = viewTransformOf(IDENTITY, { widthPx: 600, heightPx: 600, devicePixelRatio: 1 });

        const bounds = visibleBounds(transform, 30);

        expect(bounds.minimumX).toBeCloseTo(-1.1, 6);
        expect(bounds.maximumX).toBeCloseTo(1.1, 6);
        expect(bounds.minimumY).toBeCloseTo(-1.1, 6);
        expect(bounds.maximumY).toBeCloseTo(1.1, 6);
    });

    it("narrows as the view zooms in", () => {
        const viewport = { widthPx: 600, heightPx: 600, devicePixelRatio: 1 };
        const wide = visibleBounds(viewTransformOf(IDENTITY, viewport), 0);
        const close = visibleBounds(viewTransformOf(cameraView(10, 0, 0), viewport), 0);

        expect(close.maximumX - close.minimumX).toBeCloseTo((wide.maximumX - wide.minimumX) / 10, 6);
    });
});

describe("sameTransform", () => {
    it("tells a moved view or a resized surface apart", () => {
        const viewport = { widthPx: 600, heightPx: 400, devicePixelRatio: 1 };
        const transform = viewTransformOf(IDENTITY, viewport);

        expect(sameTransform(transform, viewTransformOf(Float32Array.from(IDENTITY), viewport))).toBe(true);
        expect(sameTransform(transform, viewTransformOf(cameraView(1, 0.1, 0), viewport))).toBe(false);
        expect(sameTransform(transform, viewTransformOf(IDENTITY, { ...viewport, widthPx: 601 }))).toBe(false);
        expect(sameTransform(transform, null)).toBe(false);
        expect(sameTransform(null, null)).toBe(true);
    });
});
