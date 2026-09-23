import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { bitmapOf, UNMEASURED_CANVAS_BOX, useCanvasBox } from "../../src/layout/useCanvasBox";
import { stubDevicePixelRatio } from "../support/devicePixelRatio";
import { installControllableResizeObserver, resizeTo } from "../support/resizeObserver";

function elementOfSize(width: number, height: number): HTMLDivElement {
    const element = document.createElement("div");
    vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
        x: 0,
        y: 0,
        width,
        height,
        top: 0,
        right: width,
        bottom: height,
        left: 0,
        toJSON: () => ({}),
    });
    return element;
}

describe("useCanvasBox", () => {
    it("reads nothing while the ref holds nothing", () => {
        const { result } = renderHook(() => useCanvasBox({ current: null }));

        expect(result.current).toBe(UNMEASURED_CANVAS_BOX);
    });

    it("reads the element's size and the screen's density on mount", () => {
        installControllableResizeObserver();
        stubDevicePixelRatio(2);
        const ref = { current: elementOfSize(174, 51) };

        const { result } = renderHook(() => useCanvasBox(ref));

        expect(result.current).toEqual({ width: 174, height: 51, ratio: 2 });
    });

    it("follows the observer's resizes, and keeps the same box for an equal reading", () => {
        installControllableResizeObserver();
        const ref = { current: elementOfSize(96, 28) };
        const { result } = renderHook(() => useCanvasBox(ref));
        const measured = result.current;

        act(() => {
            resizeTo(ref.current, 96, 28);
        });
        expect(result.current).toBe(measured);

        act(() => {
            resizeTo(ref.current, 250, 73);
        });
        expect(result.current).toEqual({ width: 250, height: 73, ratio: 1 });
    });
});

describe("bitmapOf", () => {
    it("backs a box with whole device pixels", () => {
        expect(bitmapOf({ width: 174.4, height: 51.2, ratio: 2 })).toEqual({ width: 349, height: 102 });
    });
});
