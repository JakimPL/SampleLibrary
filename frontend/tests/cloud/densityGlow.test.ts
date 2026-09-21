import { describe, expect, it, vi } from "vitest";

import { type GlowCanvas, glowImageOf, paintGlow } from "../../src/cloud/densityGlow";
import { viewTransformOf } from "../../src/cloud/viewTransform";

const GEOMETRY = { positions: new Float32Array([0, 0]), slots: new Float32Array([1]), count: 1 };
const PALETTE = new Uint8Array([0, 0, 0, 255, 255, 0, 0, 255]);

describe("glowImageOf", () => {
    it("answers null while the theme turns the glow off", () => {
        expect(glowImageOf(GEOMETRY, PALETTE, 0, 0)).toBeNull();
    });

    it("answers null for a batch without points", () => {
        expect(
            glowImageOf({ positions: new Float32Array(), slots: new Float32Array(), count: 0 }, PALETTE, 0, 1),
        ).toBeNull();
    });

    it("answers null where the document yields no 2D canvas", () => {
        expect(glowImageOf(GEOMETRY, PALETTE, 0, 1)).toBeNull();
    });
});

describe("paintGlow", () => {
    it("stretches the glow over the screen box its domain covers, smoothly", () => {
        const drawImage = vi.fn();
        const context: GlowCanvas = { imageSmoothingEnabled: false, drawImage };
        const image = document.createElement("canvas");
        const transform = viewTransformOf(new Float32Array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]), {
            widthPx: 600,
            heightPx: 600,
            devicePixelRatio: 2,
        });

        paintGlow(
            context,
            transform,
            { image, domain: { minimumX: -1, maximumX: 1, minimumY: -1, maximumY: 1 } },
            { width: 1200, height: 1200 },
        );

        expect(context.imageSmoothingEnabled).toBe(true);
        expect(drawImage).toHaveBeenCalledWith(image, 0, 0, 1200, 1200);
    });
});
