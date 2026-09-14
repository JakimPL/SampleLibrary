import { describe, expect, it } from "vitest";

import { gridLinesBetween, gridStep } from "../../src/cloud/gridSpacing";

describe("gridStep", () => {
    it.each([
        { pixelsPerUnit: 300, targetSpacingPx: 44 },
        { pixelsPerUnit: 12_345, targetSpacingPx: 44 },
        { pixelsPerUnit: 3, targetSpacingPx: 36 },
        { pixelsPerUnit: 88, targetSpacingPx: 44 },
    ])(
        "keeps lines at least the target apart and under twice it, at $pixelsPerUnit pixels per unit",
        ({ pixelsPerUnit, targetSpacingPx }) => {
            const step = gridStep(pixelsPerUnit, targetSpacingPx);
            const spacing = step * pixelsPerUnit;

            expect(spacing).toBeGreaterThanOrEqual(targetSpacingPx);
            expect(spacing).toBeLessThan(targetSpacingPx * 2);
            expect(Number.isInteger(Math.log2(step))).toBe(true);
        },
    );
});

describe("gridLinesBetween", () => {
    it("lists every step within the range", () => {
        expect(gridLinesBetween(-0.3, 0.55, 0.25).map((line) => line.value)).toEqual([-0.25, 0, 0.25, 0.5]);
    });

    it("ranks every fourth line a beat and every sixteenth a measure, below zero too", () => {
        const lines = gridLinesBetween(-17, 17, 1);
        const rankOf = (value: number): string | undefined => lines.find((line) => line.value === value)?.rank;

        expect(rankOf(0)).toBe("measure");
        expect(rankOf(16)).toBe("measure");
        expect(rankOf(-16)).toBe("measure");
        expect(rankOf(4)).toBe("beat");
        expect(rankOf(-12)).toBe("beat");
        expect(rankOf(1)).toBe("row");
        expect(rankOf(-5)).toBe("row");
    });

    it("keeps a measure line a measure line through a zoom that halves the step", () => {
        const coarse = gridLinesBetween(0, 64, 4).filter((line) => line.rank === "measure");
        const fine = gridLinesBetween(0, 64, 2);

        for (const measure of coarse) {
            expect(fine.find((line) => line.value === measure.value)?.rank).toBe("measure");
        }
    });
});
