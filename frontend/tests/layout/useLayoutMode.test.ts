import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { COARSE_POINTER_MEDIA_QUERY, PHONE_MEDIA_QUERY } from "../../src/layout/layoutMode";
import { useLayoutMode } from "../../src/layout/useLayoutMode";
import { stubMatchMedia } from "../support/matchMedia";

describe("useLayoutMode", () => {
    it("reads the workspace with a pointer while no query matches", () => {
        stubMatchMedia(new Set());

        const { result } = renderHook(() => useLayoutMode());

        expect(result.current).toEqual({ layout: "workspace", input: "pointer" });
    });

    it("reads the phone shell while the phone query matches", () => {
        stubMatchMedia(new Set([PHONE_MEDIA_QUERY]));

        const { result } = renderHook(() => useLayoutMode());

        expect(result.current.layout).toBe("phone");
    });

    it("reads touch for a coarse pointer", () => {
        stubMatchMedia(new Set([COARSE_POINTER_MEDIA_QUERY]));

        const { result } = renderHook(() => useLayoutMode());

        expect(result.current.input).toBe("touch");
    });

    it("follows a change of the phone query while mounted", () => {
        const media = stubMatchMedia(new Set());
        const { result } = renderHook(() => useLayoutMode());

        act(() => {
            media.emit(PHONE_MEDIA_QUERY, true);
        });
        expect(result.current.layout).toBe("phone");

        act(() => {
            media.emit(PHONE_MEDIA_QUERY, false);
        });
        expect(result.current.layout).toBe("workspace");
    });

    it("hands back the same signal object while nothing changed", () => {
        const media = stubMatchMedia(new Set());
        const { result, rerender } = renderHook(() => useLayoutMode());
        const first = result.current;

        rerender();
        act(() => {
            media.emit(COARSE_POINTER_MEDIA_QUERY, false);
        });

        expect(result.current).toBe(first);
    });
});
