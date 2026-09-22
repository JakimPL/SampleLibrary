import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useCloudDotsStore } from "../../src/cloud/cloudDotsStore";
import type { PointStyle } from "../../src/cloud/cloudRenderSettings";
import { plainDotStyle, usePlainDots } from "../../src/cloud/plainDots";

const POINT: PointStyle = {
    shape: "circle",
    sizePx: 2.5,
    substrateSizePx: 1.8,
    opacity: 0.9,
    substrateOpacity: 0.6,
    selectedExtraSizePx: 2,
    outlineWidthPx: 0,
    scaleMode: "asinh",
};

describe("usePlainDots", () => {
    it("draws plain dots once chosen, and leaves the scatterplot its job where no WebGL says otherwise", () => {
        const { result } = renderHook(() => usePlainDots());
        expect(result.current).toBeNull();

        act(() => {
            useCloudDotsStore.getState().setDots("plain");
        });

        expect(result.current).toBe("chosen");
    });
});

describe("plainDotStyle", () => {
    it("draws every point as a filled dot the size the theme draws its points, the substrate as faint", () => {
        expect(plainDotStyle(POINT)).toEqual({
            mode: "always",
            sizePx: 3,
            lineWidthPx: 0,
            fillOpacity: 1,
            substrateOpacity: 0.6,
        });
    });

    it("keeps a dot at least two pixels across", () => {
        expect(plainDotStyle({ ...POINT, sizePx: 0.4 }).sizePx).toBe(2);
    });
});
