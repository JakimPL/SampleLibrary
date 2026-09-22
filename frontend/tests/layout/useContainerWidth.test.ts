import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useContainerWidth } from "../../src/layout/useContainerWidth";
import { installControllableResizeObserver, resizeTo } from "../support/resizeObserver";

function elementOfWidth(width: number): HTMLDivElement {
    const element = document.createElement("div");
    vi.spyOn(element, "getBoundingClientRect").mockReturnValue({
        x: 0,
        y: 0,
        width,
        height: 0,
        top: 0,
        right: width,
        bottom: 0,
        left: 0,
        toJSON: () => ({}),
    });
    return element;
}

describe("useContainerWidth", () => {
    it("reads null while the ref holds nothing", () => {
        const { result } = renderHook(() => useContainerWidth({ current: null }));

        expect(result.current).toBeNull();
    });

    it("reads the element's width on mount, in whole pixels", () => {
        installControllableResizeObserver();
        const ref = { current: elementOfWidth(383.6) };

        const { result } = renderHook(() => useContainerWidth(ref));

        expect(result.current).toBe(384);
    });

    it("follows the observer's resizes", () => {
        installControllableResizeObserver();
        const ref = { current: elementOfWidth(600) };
        const { result } = renderHook(() => useContainerWidth(ref));

        act(() => {
            resizeTo(ref.current, 320, 800);
        });

        expect(result.current).toBe(320);
    });
});
