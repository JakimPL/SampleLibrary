import { describe, expect, it } from "vitest";

import type { CloudColors } from "../../src/cloud/cloudRenderSettings";
import type { CloudEntityPoint } from "../../src/cloud/geometry";
import { type PointColoring, SUBSTRATE_ONLY_COLORING, SUBSTRATE_SLOT } from "../../src/cloud/labelColoring";
import { drawOrder, paletteColors, slotPoints, slotValues } from "../../src/cloud/pointPalette";

const COLORS: CloudColors = {
    background: "#000000",
    point: "#ffffff",
    selected: "#ffff00",
    hover: "#ffffff",
    uncategorized: "#333333",
    labels: { lightness: 0.7, chroma: 0.15 },
};

function sample(hashCharacter: string): CloudEntityPoint {
    return { ref: { kind: "sample", hash: hashCharacter.repeat(64) }, x: 0, y: 0 };
}

/** Samples "1" and "3" carry painted tags in slots 1 and 2; every other sample lies on the ground. */
const PAINTED: PointColoring = {
    slotByHash: new Map([
        ["1".repeat(64), 1],
        ["3".repeat(64), 2],
    ]),
    ranks: [4, 9],
};

describe("slotPoints", () => {
    it("answers null for the module cloud, drawn in one flat color", () => {
        const module: CloudEntityPoint = { ref: { kind: "module", hash: "m".repeat(64) }, x: 0, y: 0 };

        expect(slotPoints([module], PAINTED)).toBeNull();
        expect(slotPoints([], PAINTED)).toBeNull();
    });

    it("gives each point its painted tag's slot and every other point the substrate's", () => {
        const slotting = slotPoints([sample("1"), sample("2")], PAINTED);

        expect(Array.from(slotting?.slots ?? [])).toEqual([1, SUBSTRATE_SLOT]);
        expect(slotting?.substrateSlot).toBe(SUBSTRATE_SLOT);
        expect(slotting?.slotCount).toBe(3);
    });

    it("lays every sample on the ground while no tag is painted yet", () => {
        const slotting = slotPoints([sample("1"), sample("2")], SUBSTRATE_ONLY_COLORING);

        expect(Array.from(slotting?.slots ?? [])).toEqual([SUBSTRATE_SLOT, SUBSTRATE_SLOT]);
        expect(slotting?.slotCount).toBe(1);
    });
});

describe("paletteColors", () => {
    it("paints the substrate first and one color per painted tag after it", () => {
        const palette = paletteColors(PAINTED, COLORS);

        expect(palette).toHaveLength(3);
        expect(palette[0]).toBe(COLORS.uncategorized);
        expect(new Set(palette).size).toBe(3);
    });
});

describe("slotValues", () => {
    it("gives the substrate's slot its own value and every other slot the named points' one", () => {
        const slotting = slotPoints([sample("1"), sample("2")], PAINTED);
        if (slotting === null) {
            throw new Error("a sample batch has slots");
        }

        const opacities = slotValues(slotting, 0.9, 0.4);

        expect(opacities).toEqual([0.4, 0.9, 0.9]);
    });
});

describe("drawOrder", () => {
    it("draws the substrate's points first, each group in its own order", () => {
        const slotting = slotPoints([sample("1"), sample("2"), sample("3"), sample("4")], PAINTED);
        if (slotting === null) {
            throw new Error("a sample batch has slots");
        }

        expect(drawOrder(slotting)).toEqual([1, 3, 0, 2]);
    });
});
