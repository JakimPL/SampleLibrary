import { describe, expect, it } from "vitest";

import type { WaveformPeak } from "../../src/api/samples";
import { layoutWaveformBars } from "../../src/samples/waveformLayout";

function peak(minimum: number, maximum: number): WaveformPeak {
    return { minimum, maximum };
}

describe("layoutWaveformBars", () => {
    it("returns nothing for an empty input", () => {
        expect(layoutWaveformBars([], 800, 160)).toEqual([]);
    });

    it("spans the full canvas width across the given number of bars", () => {
        const bars = layoutWaveformBars([peak(-1, 1), peak(-1, 1)], 800, 160);

        expect(bars.map((bar) => bar.x)).toEqual([0, 400]);
        expect(bars.every((bar) => bar.width === 400)).toBe(true);
    });

    it("maps full-amplitude peaks to the canvas's own top and bottom edges", () => {
        const [bar] = layoutWaveformBars([peak(-1, 1)], 800, 160);

        expect(bar).toBeDefined();
        expect(bar?.yTop).toBe(0);
        expect(bar?.yBottom).toBe(160);
    });

    it("maps silence to a flat line through the vertical center", () => {
        const [bar] = layoutWaveformBars([peak(0, 0)], 800, 160);

        expect(bar?.yTop).toBe(80);
        expect(bar?.yBottom).toBe(80);
    });
});
