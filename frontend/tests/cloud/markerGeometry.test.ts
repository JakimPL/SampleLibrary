import { describe, expect, it } from "vitest";

import {
    crispSquare,
    devicePixels,
    lineBetweenMarkers,
    type MarkerAppearance,
    markerReach,
    ringFrame,
    snapToDevicePixel,
} from "../../src/cloud/markerGeometry";

function isWhole(value: number): boolean {
    return Math.abs(value - Math.round(value)) < 1e-9;
}

describe("devicePixels", () => {
    it.each([
        { lengthPx: 7, devicePixelRatio: 1, expected: 7 },
        { lengthPx: 7, devicePixelRatio: 1.75, expected: 12 },
        { lengthPx: 1, devicePixelRatio: 1.25, expected: 1 },
        { lengthPx: 0.2, devicePixelRatio: 1, expected: 1 },
    ])(
        "counts $lengthPx CSS pixels at a ratio of $devicePixelRatio as $expected",
        ({ lengthPx, devicePixelRatio, expected }) => {
            expect(devicePixels(lengthPx, devicePixelRatio)).toBe(expected);
        },
    );
});

describe("snapToDevicePixel", () => {
    it("moves a coordinate onto a device pixel boundary", () => {
        expect(isWhole(snapToDevicePixel(10.3, 1.75) * 1.75)).toBe(true);
        expect(snapToDevicePixel(10.3, 1)).toBe(10);
    });
});

describe("crispSquare", () => {
    it("frames a one-pixel square around a point at a ratio of one", () => {
        expect(crispSquare([10.7, 20.2], 7, 1, 1)).toEqual({ x: 7.5, y: 17.5, side: 6, strokeWidth: 1 });
    });

    it.each([
        { center: [10.7, 20.2] as const, devicePixelRatio: 1 },
        { center: [3.14, 99.9] as const, devicePixelRatio: 1.25 },
        { center: [250.4, 13.6] as const, devicePixelRatio: 1.75 },
        { center: [0.5, 0.5] as const, devicePixelRatio: 2 },
    ])(
        "puts the outer edges and the stroke on whole device pixels at a ratio of $devicePixelRatio",
        ({ center, devicePixelRatio }) => {
            const frame = crispSquare(center, 7, 1, devicePixelRatio);
            const outerLeft = (frame.x - frame.strokeWidth / 2) * devicePixelRatio;
            const outerTop = (frame.y - frame.strokeWidth / 2) * devicePixelRatio;
            const outerSide = (frame.side + frame.strokeWidth) * devicePixelRatio;

            expect(isWhole(outerLeft)).toBe(true);
            expect(isWhole(outerTop)).toBe(true);
            expect(Math.round(outerSide)).toBe(devicePixels(7, devicePixelRatio));
            expect(Math.round(frame.strokeWidth * devicePixelRatio)).toBe(devicePixels(1, devicePixelRatio));
            expect(
                Math.abs(outerLeft / devicePixelRatio + outerSide / devicePixelRatio / 2 - center[0]),
            ).toBeLessThanOrEqual(1 / devicePixelRatio);
        },
    );
});

describe("ringFrame", () => {
    it("runs the stroke just inside the ring's outer size", () => {
        expect(ringFrame(13, 1.5)).toEqual({ radius: 5.75, strokeWidth: 1.5 });
    });
});

describe("markerReach", () => {
    const RING: MarkerAppearance = {
        shape: "circle",
        sizePx: 12,
        lineWidthPx: 1,
        casingWidthPx: 0,
        devicePixelRatio: 1,
    };
    const SQUARE: MarkerAppearance = { ...RING, shape: "square" };

    it("reaches a ring's radius in every direction", () => {
        expect(markerReach(RING, 1, 0)).toBe(6);
        expect(markerReach(RING, 3, 4)).toBe(6);
    });

    it("reaches a square's side straight across and its corner along the diagonal", () => {
        expect(markerReach(SQUARE, 0, -5)).toBe(6);
        expect(markerReach(SQUARE, 1, 1)).toBeCloseTo(6 * Math.SQRT2);
    });
});

describe("lineBetweenMarkers", () => {
    const RING: MarkerAppearance = {
        shape: "circle",
        sizePx: 10,
        lineWidthPx: 1,
        casingWidthPx: 0,
        devicePixelRatio: 1,
    };

    it("stops short of the marker at each marked end", () => {
        expect(lineBetweenMarkers([0, 0], [100, 0], RING, true)).toEqual([
            [5, 0],
            [95, 0],
        ]);
    });

    it("runs to an unmarked end", () => {
        expect(lineBetweenMarkers([0, 0], [100, 0], RING, false)).toEqual([
            [5, 0],
            [100, 0],
        ]);
    });

    it("draws nothing between markers that touch", () => {
        expect(lineBetweenMarkers([0, 0], [8, 0], RING, true)).toBeNull();
    });
});
