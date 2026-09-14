import { describe, expect, it } from "vitest";

import type { CloudColors } from "../../src/cloud/cloudRenderSettings";
import type { CloudEntityPoint } from "../../src/cloud/geometry";
import type { PointColoring } from "../../src/cloud/labelColoring";
import { drawOrder, paletteColors, slotPoints, slotValues } from "../../src/cloud/pointPalette";
import { CATEGORY_ORDER, categoryIndex } from "../../src/samples/category";

const COLORS: CloudColors = {
    background: "#000000",
    point: "#ffffff",
    selected: "#ffff00",
    hover: "#ffffff",
    uncategorized: "#333333",
    categories: CATEGORY_ORDER.map((_, index) => `#0000${index.toString(16).padStart(2, "0")}`),
    labels: { lightness: 0.7, chroma: 0.15 },
};

function sample(hashCharacter: string, category: CloudEntityPoint["category"]): CloudEntityPoint {
    return { ref: { kind: "sample", hash: hashCharacter.repeat(64) }, x: 0, y: 0, ...(category && { category }) };
}

const CATEGORY_COLORING: PointColoring = { kind: "category" };

describe("slotPoints", () => {
    it("answers null for a batch drawn in one flat color", () => {
        const module: CloudEntityPoint = { ref: { kind: "module", hash: "m".repeat(64) }, x: 0, y: 0 };

        expect(slotPoints([module], CATEGORY_COLORING)).toBeNull();
        expect(slotPoints([], CATEGORY_COLORING)).toBeNull();
    });

    it("gives each point its category's slot, the uncategorized one being the substrate", () => {
        const slotting = slotPoints([sample("1", "snare"), sample("2", "uncategorized")], CATEGORY_COLORING);

        expect(Array.from(slotting?.slots ?? [])).toEqual([categoryIndex("snare"), categoryIndex("uncategorized")]);
        expect(slotting?.substrateSlot).toBe(categoryIndex("uncategorized"));
        expect(slotting?.slotCount).toBe(CATEGORY_ORDER.length);
    });

    it("gives each labeled point its painted tag's slot and every other point the substrate's", () => {
        const coloring: PointColoring = { kind: "label", slotByHash: new Map([["2".repeat(64), 2]]), ranks: [4, 9] };

        const slotting = slotPoints([sample("1", "kick"), sample("2", "kick")], coloring);

        expect(Array.from(slotting?.slots ?? [])).toEqual([0, 2]);
        expect(slotting?.substrateSlot).toBe(0);
        expect(slotting?.slotCount).toBe(3);
    });
});

describe("paletteColors", () => {
    it("paints every category in its own color", () => {
        expect(paletteColors(CATEGORY_COLORING, COLORS)).toEqual(COLORS.categories);
    });

    it("paints the substrate first and one color per painted tag after it", () => {
        const coloring: PointColoring = { kind: "label", slotByHash: new Map(), ranks: [4, 9] };

        const palette = paletteColors(coloring, COLORS);

        expect(palette).toHaveLength(3);
        expect(palette[0]).toBe(COLORS.uncategorized);
        expect(new Set(palette).size).toBe(3);
    });
});

describe("slotValues", () => {
    it("gives the substrate's slot its own value and every other slot the named points' one", () => {
        const slotting = slotPoints([sample("1", "kick"), sample("2", "uncategorized")], CATEGORY_COLORING);
        if (slotting === null) {
            throw new Error("a categorized batch has slots");
        }

        const opacities = slotValues(slotting, 0.9, 0.4);

        expect(opacities).toHaveLength(CATEGORY_ORDER.length);
        expect(opacities[slotting.substrateSlot]).toBe(0.4);
        expect(opacities.filter((opacity) => opacity === 0.9)).toHaveLength(CATEGORY_ORDER.length - 1);
    });
});

describe("drawOrder", () => {
    it("draws the substrate's points first, each group in its own order", () => {
        const slotting = slotPoints(
            [sample("1", "kick"), sample("2", "uncategorized"), sample("3", "pad"), sample("4", "uncategorized")],
            CATEGORY_COLORING,
        );
        if (slotting === null) {
            throw new Error("a categorized batch has slots");
        }

        expect(drawOrder(slotting)).toEqual([1, 3, 0, 2]);
    });
});
