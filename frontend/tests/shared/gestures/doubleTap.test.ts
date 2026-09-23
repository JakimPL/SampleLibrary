import { describe, expect, it } from "vitest";

import { createDoubleTapRecognizer } from "../../../src/shared/gestures/doubleTap";

const THRESHOLDS = { intervalMs: 350, slopPx: 10 };

describe("createDoubleTapRecognizer", () => {
    it("completes on a second tap in the same place within the interval", () => {
        const recognizer = createDoubleTapRecognizer(THRESHOLDS);

        expect(recognizer.tap(40, 60, 1000)).toBe(false);
        expect(recognizer.tap(44, 57, 1300)).toBe(true);
    });

    it("begins a new pair after one completes, so a third tap is a first again", () => {
        const recognizer = createDoubleTapRecognizer(THRESHOLDS);
        recognizer.tap(40, 60, 1000);
        recognizer.tap(40, 60, 1200);

        expect(recognizer.tap(40, 60, 1400)).toBe(false);
        expect(recognizer.tap(40, 60, 1600)).toBe(true);
    });

    it("takes a late tap as a first, which the next may pair with", () => {
        const recognizer = createDoubleTapRecognizer(THRESHOLDS);
        recognizer.tap(40, 60, 1000);

        expect(recognizer.tap(40, 60, 1351)).toBe(false);
        expect(recognizer.tap(40, 60, 1500)).toBe(true);
    });

    it("takes a tap past the slop as a first", () => {
        const recognizer = createDoubleTapRecognizer(THRESHOLDS);
        recognizer.tap(0, 0, 1000);

        expect(recognizer.tap(0, THRESHOLDS.slopPx + 1, 1100)).toBe(false);
        expect(recognizer.tap(0, THRESHOLDS.slopPx + 1, 1200)).toBe(true);
    });
});
