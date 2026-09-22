import { describe, expect, it } from "vitest";

import {
    COARSE_POINTER_MEDIA_QUERY,
    inputModeOf,
    layoutModeOf,
    PHONE_MEDIA_QUERY,
    WORKSPACE_MIN_HEIGHT_PX,
    WORKSPACE_MIN_WIDTH_PX,
} from "../../src/layout/layoutMode";

interface LayoutCase {
    readonly phoneMatches: boolean;
    readonly expected: "phone" | "workspace";
}

interface InputCase {
    readonly coarsePointer: boolean;
    readonly expected: "touch" | "pointer";
}

describe("layoutModeOf", () => {
    it.each<LayoutCase>([
        { phoneMatches: true, expected: "phone" },
        { phoneMatches: false, expected: "workspace" },
    ])("reads $expected when the phone query matches: $phoneMatches", ({ phoneMatches, expected }) => {
        expect(layoutModeOf(phoneMatches)).toBe(expected);
    });
});

describe("inputModeOf", () => {
    it.each<InputCase>([
        { coarsePointer: false, expected: "pointer" },
        { coarsePointer: true, expected: "touch" },
    ])("reads $expected for a coarse pointer: $coarsePointer", ({ coarsePointer, expected }) => {
        expect(inputModeOf(coarsePointer)).toBe(expected);
    });
});

describe("the media queries", () => {
    it("names the workspace thresholds in the phone query", () => {
        expect(PHONE_MEDIA_QUERY).toContain(`${String(WORKSPACE_MIN_WIDTH_PX)}px`);
        expect(PHONE_MEDIA_QUERY).toContain(`${String(WORKSPACE_MIN_HEIGHT_PX)}px`);
    });

    it("asks about the primary pointer alone", () => {
        expect(COARSE_POINTER_MEDIA_QUERY).toContain("pointer");
        expect(COARSE_POINTER_MEDIA_QUERY).not.toContain("hover");
    });
});
