import { describe, expect, it } from "vitest";

import { drawsFloat, needsPlainDots, NO_WEBGL, probeFloatRendering } from "../../src/cloud/floatRendering";

const RENDERER_PARAMETER = 0x9246;
const ALL_EXTENSIONS = ["OES_texture_float", "WEBGL_color_buffer_float", "EXT_float_blend"];

/** A canvas whose WebGL offers the named extensions, or no WebGL at all for `null`. */
function canvasWith(extensions: readonly string[] | null, namesRenderer = true): HTMLCanvasElement {
    const canvas = document.createElement("canvas");
    const gl =
        extensions === null
            ? null
            : {
                  getExtension: (name: string): object | null => {
                      if (name === "WEBGL_debug_renderer_info") {
                          return namesRenderer ? { UNMASKED_RENDERER_WEBGL: RENDERER_PARAMETER } : null;
                      }
                      if (name === "WEBGL_lose_context") {
                          return { loseContext: (): undefined => undefined };
                      }
                      return extensions.includes(name) ? {} : null;
                  },
                  getParameter: (): string => "Test GPU",
              };
    Object.defineProperty(canvas, "getContext", { value: () => gl });
    return canvas;
}

describe("probeFloatRendering", () => {
    it("reports no WebGL where the canvas gives none", () => {
        expect(probeFloatRendering(canvasWith(null))).toEqual(NO_WEBGL);
    });

    it("reads the three float extensions and the GPU's name", () => {
        expect(probeFloatRendering(canvasWith(ALL_EXTENSIONS))).toEqual({
            webgl: true,
            textureFloat: true,
            colorBufferFloat: true,
            floatBlend: true,
            renderer: "Test GPU",
        });
    });

    it("notes a missing extension, and a browser that keeps the GPU's name to itself", () => {
        const support = probeFloatRendering(canvasWith(["OES_texture_float", "WEBGL_color_buffer_float"], false));

        expect(support).toMatchObject({ webgl: true, floatBlend: false, renderer: null });
    });
});

describe("drawsFloat and needsPlainDots", () => {
    it("lets the scatterplot draw where every float extension is there", () => {
        const support = probeFloatRendering(canvasWith(ALL_EXTENSIONS));

        expect(drawsFloat(support)).toBe(true);
        expect(needsPlainDots(support)).toBe(false);
    });

    it("calls for plain dots where WebGL blends no float buffers", () => {
        const support = probeFloatRendering(canvasWith(["OES_texture_float", "WEBGL_color_buffer_float"]));

        expect(drawsFloat(support)).toBe(false);
        expect(needsPlainDots(support)).toBe(true);
    });

    it("calls for nothing where there is no WebGL to draw with", () => {
        expect(needsPlainDots(NO_WEBGL)).toBe(false);
    });
});
