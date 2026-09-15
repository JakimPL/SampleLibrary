import { describe, expect, it } from "vitest";

import type { CloudEntityPoint } from "../../src/cloud/geometry";
import { SUBSTRATE_SLOT } from "../../src/cloud/labelColoring";
import { nodeGeometryOf, nodePaletteOf } from "../../src/cloud/nodeGeometry";
import { slotPoints } from "../../src/cloud/pointPalette";

const KICK_SLOT = 1;
const PAD_SLOT = 2;

function sample(hashCharacter: string, x: number, y: number): CloudEntityPoint {
    return { ref: { kind: "sample", hash: hashCharacter.repeat(64) }, x, y };
}

describe("nodeGeometryOf", () => {
    it("lays the substrate's nodes out first, each with its position and slot", () => {
        const points = [sample("1", 0.1, 0.2), sample("2", 0.3, 0.4), sample("3", 0.5, 0.6)];
        const coloring = {
            slotByHash: new Map([
                ["1".repeat(64), KICK_SLOT],
                ["3".repeat(64), PAD_SLOT],
            ]),
            ranks: [0, 1],
        };

        const geometry = nodeGeometryOf(points, slotPoints(points, coloring));

        expect(geometry.count).toBe(3);
        expect(Array.from(geometry.positions)).toEqual(
            [0.3, 0.4, 0.1, 0.2, 0.5, 0.6].map((value) => Math.fround(value)),
        );
        expect(Array.from(geometry.slots)).toEqual([SUBSTRATE_SLOT, KICK_SLOT, PAD_SLOT]);
    });

    it("keeps a flat batch in its own order, every node in slot zero", () => {
        const points: CloudEntityPoint[] = [
            { ref: { kind: "module", hash: "m".repeat(64) }, x: -0.5, y: 0.5 },
            { ref: { kind: "module", hash: "n".repeat(64) }, x: 0.25, y: -0.75 },
        ];

        const geometry = nodeGeometryOf(points, null);

        expect(Array.from(geometry.positions)).toEqual([-0.5, 0.5, 0.25, -0.75]);
        expect(Array.from(geometry.slots)).toEqual([0, 0]);
    });
});

describe("nodePaletteOf", () => {
    it("writes one RGBA quadruple per slot, the substrate's at its own opacity", () => {
        const palette = nodePaletteOf(["#ff0000", "#00ff00"], 1, 0.5);

        expect(Array.from(palette)).toEqual([255, 0, 0, 255, 0, 255, 0, 128]);
    });

    it("paints a color it cannot read transparent", () => {
        expect(Array.from(nodePaletteOf(["papayawhip"], null, 1))).toEqual([0, 0, 0, 0]);
    });
});
