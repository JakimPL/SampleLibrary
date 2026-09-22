import { describe, expect, it } from "vitest";

import { fitColumns, type FittableColumn, FLEXIBLE_COLUMN_MINIMUM_PX } from "../../src/shared/columnFit";

const COLUMNS: readonly FittableColumn<"waveform" | "name" | "category" | "size">[] = [
    { id: "waveform", widthPx: 76, dropOrder: null },
    { id: "name", widthPx: null, dropOrder: null },
    { id: "category", widthPx: 144, dropOrder: 2 },
    { id: "size", widthPx: 80, dropOrder: 1 },
];

const EVERY_WIDTH = 76 + FLEXIBLE_COLUMN_MINIMUM_PX + 144 + 80;

interface FitCase {
    readonly width: number;
    readonly expected: readonly string[];
}

describe("fitColumns", () => {
    it.each<FitCase>([
        { width: EVERY_WIDTH, expected: ["waveform", "name", "category", "size"] },
        { width: EVERY_WIDTH - 1, expected: ["waveform", "name", "category"] },
        { width: EVERY_WIDTH - 80 - 1, expected: ["waveform", "name"] },
        { width: 0, expected: ["waveform", "name"] },
    ])("keeps $expected at $width px", ({ width, expected }) => {
        expect([...fitColumns(COLUMNS, width)]).toEqual(expected);
    });

    it("lets the columns leave in their declared order whatever order they are listed in", () => {
        const reversed = [...COLUMNS].reverse();

        expect([...fitColumns(reversed, EVERY_WIDTH - 1)].sort()).toEqual(["category", "name", "waveform"]);
    });
});
