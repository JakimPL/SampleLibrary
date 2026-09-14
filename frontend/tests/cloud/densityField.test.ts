import { describe, expect, it } from "vitest";

import { accumulateDensity, blurDensity, glowPixels } from "../../src/cloud/densityField";
import type { NodeGeometry } from "../../src/cloud/nodeGeometry";

const DOMAIN = { minimumX: -1, maximumX: 1, minimumY: -1, maximumY: 1 };
const PALETTE = new Uint8Array([100, 100, 100, 255, 255, 0, 0, 255, 0, 0, 255, 255]);

function geometry(nodes: readonly (readonly [number, number, number])[]): NodeGeometry {
    return {
        positions: new Float32Array(nodes.flatMap(([x, y]) => [x, y])),
        slots: new Float32Array(nodes.map(([, , slot]) => slot)),
        count: nodes.length,
    };
}

function sum(values: Float32Array): number {
    return values.reduce((total, value) => total + value, 0);
}

describe("accumulateDensity", () => {
    it("counts each node into its cell, rows from the top, with its color's channels", () => {
        const field = accumulateDensity(
            geometry([
                [-0.9, 0.9, 1],
                [-0.8, 0.8, 1],
                [0.9, -0.9, 2],
            ]),
            PALETTE,
            4,
            DOMAIN,
            null,
        );

        expect(field.counts[0]).toBe(2);
        expect(field.red[0]).toBe(510);
        expect(field.counts[15]).toBe(1);
        expect(field.blue[15]).toBe(255);
        expect(sum(field.counts)).toBe(3);
    });

    it("leaves out the nodes outside the domain and those in the excluded slot", () => {
        const field = accumulateDensity(
            geometry([
                [0.1, 0.1, 0],
                [0.2, 0.2, 1],
                [3, 3, 1],
            ]),
            PALETTE,
            4,
            DOMAIN,
            0,
        );

        expect(sum(field.counts)).toBe(1);
    });
});

describe("blurDensity", () => {
    it("spreads a lone point to its neighbors and keeps its weight away from the edges", () => {
        const field = accumulateDensity(geometry([[0.01, 0.01, 1]]), PALETTE, 32, DOMAIN, null);

        const blurred = blurDensity(field, 2, 2);

        expect(sum(blurred.counts)).toBeCloseTo(1, 5);
        expect(blurred.counts.filter((count) => count > 0).length).toBeGreaterThan(1);
    });

    it("keeps a cell's average color while blurring", () => {
        const field = accumulateDensity(geometry([[0.01, 0.01, 1]]), PALETTE, 16, DOMAIN, null);

        const blurred = blurDensity(field, 1, 1);
        const cell = blurred.counts.findIndex((count) => count > 0);

        expect((blurred.red[cell] ?? 0) / (blurred.counts[cell] ?? 1)).toBeCloseTo(255, 3);
    });
});

describe("glowPixels", () => {
    it("paints each cell in its average color, the densest at full opacity and a sparser one fainter but in view", () => {
        const nodes = [
            ...Array.from({ length: 1000 }, (): readonly [number, number, number] => [-0.9, 0.9, 1]),
            [0.9, -0.9, 2] as const,
        ];
        const field = accumulateDensity(geometry(nodes), PALETTE, 4, DOMAIN, null);

        const pixels = glowPixels(field, 0.5);

        expect(Array.from(pixels.slice(0, 4))).toEqual([255, 0, 0, 128]);
        expect(pixels[15 * 4 + 2]).toBe(255);
        expect(pixels[15 * 4 + 3]).toBeGreaterThan(10);
        expect(pixels[15 * 4 + 3]).toBeLessThan(128);
        expect(pixels[5 * 4 + 3]).toBe(0);
    });

    it("answers transparent pixels for an empty field", () => {
        const field = accumulateDensity(geometry([]), PALETTE, 2, DOMAIN, null);

        expect(Array.from(glowPixels(field, 1))).toEqual(Array.from({ length: 16 }, () => 0));
    });
});
