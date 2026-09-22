import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { applyLayoutSignal, useLayoutAttributes } from "../../src/layout/layoutAttributes";
import { COARSE_POINTER_MEDIA_QUERY, PHONE_MEDIA_QUERY } from "../../src/layout/layoutMode";
import { stubMatchMedia } from "../support/matchMedia";

describe("applyLayoutSignal", () => {
    it("writes both modes onto the element", () => {
        const root = document.createElement("div");

        applyLayoutSignal(root, { layout: "phone", input: "touch" });

        expect(root.dataset.layout).toBe("phone");
        expect(root.dataset.input).toBe("touch");
    });
});

describe("useLayoutAttributes", () => {
    it("keeps the document root's attributes equal to the live signal", () => {
        const media = stubMatchMedia(new Set([COARSE_POINTER_MEDIA_QUERY]));
        renderHook(() => {
            useLayoutAttributes();
        });

        expect(document.documentElement.dataset.layout).toBe("workspace");
        expect(document.documentElement.dataset.input).toBe("touch");

        act(() => {
            media.emit(PHONE_MEDIA_QUERY, true);
        });

        expect(document.documentElement.dataset.layout).toBe("phone");
    });
});
