import { describe, expect, it } from "vitest";

import { labelColor, labelHue, readLabelPaletteParameters } from "../../src/theme/labelPalette";

const HEX_COLOR = /^#[0-9a-f]{6}$/;
const PARAMETERS = { lightness: 0.6, chroma: 0.15 };
const TAG_COUNT = 40;

describe("labelColor", () => {
    it("paints every rank as a hex triplet", () => {
        for (let rank = 0; rank < TAG_COUNT; rank += 1) {
            expect(labelColor(rank, PARAMETERS)).toMatch(HEX_COLOR);
        }
    });

    it("gives distinct ranks distinct colors, and one rank always the same color", () => {
        const colors = Array.from({ length: TAG_COUNT }, (_, rank) => labelColor(rank, PARAMETERS));

        expect(new Set(colors).size).toBe(TAG_COUNT);
        expect(labelColor(7, PARAMETERS)).toBe(colors[7]);
    });

    it("keeps successive hues far apart", () => {
        for (let rank = 0; rank < TAG_COUNT; rank += 1) {
            const step = Math.abs(labelHue(rank + 1) - labelHue(rank));
            expect(Math.min(step, 360 - step)).toBeGreaterThan(90);
        }
    });

    it("paints lighter under a theme asking for more lightness", () => {
        const dim = labelColor(0, { lightness: 0.4, chroma: 0.1 });
        const bright = labelColor(0, { lightness: 0.8, chroma: 0.1 });

        expect(Number.parseInt(bright.slice(1, 3), 16)).toBeGreaterThan(Number.parseInt(dim.slice(1, 3), 16));
    });
});

describe("readLabelPaletteParameters", () => {
    it("falls back to usable parameters where the theme declares none", () => {
        const parameters = readLabelPaletteParameters();

        expect(parameters.lightness).toBeGreaterThan(0);
        expect(parameters.lightness).toBeLessThan(1);
        expect(parameters.chroma).toBeGreaterThan(0);
    });
});
