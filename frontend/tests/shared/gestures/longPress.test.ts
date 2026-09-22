import { describe, expect, it, vi } from "vitest";

import { createLongPressRecognizer, type LongPressTimer } from "../../../src/shared/gestures/longPress";

const THRESHOLDS = { holdMs: 500, slopPx: 10 };

interface Harness {
    readonly fire: () => void;
    readonly callOffs: number;
}

/** A timer whose scheduled call is fired by the test, counting how often a press called it off. */
function fakeTimer(): { readonly timer: LongPressTimer; readonly harness: () => Harness } {
    let scheduled: (() => void) | null = null;
    let callOffs = 0;
    const timer: LongPressTimer = (fire) => {
        scheduled = fire;
        return (): void => {
            scheduled = null;
            callOffs += 1;
        };
    };
    return {
        timer,
        harness: () => ({
            fire: (): void => {
                scheduled?.();
            },
            callOffs,
        }),
    };
}

describe("createLongPressRecognizer", () => {
    it("fires once the finger has rested for the hold time, at the point pressed", () => {
        const { timer, harness } = fakeTimer();
        const onLongPress = vi.fn();
        const recognizer = createLongPressRecognizer(THRESHOLDS, timer, onLongPress);

        recognizer.press(1, 40, 60);
        expect(recognizer.fired()).toBe(false);
        harness().fire();

        expect(onLongPress).toHaveBeenCalledWith(40, 60);
        expect(recognizer.fired()).toBe(true);
    });

    it("calls the press off when the finger drifts past the slop", () => {
        const { timer, harness } = fakeTimer();
        const onLongPress = vi.fn();
        const recognizer = createLongPressRecognizer(THRESHOLDS, timer, onLongPress);

        recognizer.press(1, 0, 0);
        recognizer.move(1, 0, THRESHOLDS.slopPx + 1);
        harness().fire();

        expect(onLongPress).not.toHaveBeenCalled();
        expect(harness().callOffs).toBe(1);
    });

    it("keeps a press that drifts within the slop", () => {
        const { timer, harness } = fakeTimer();
        const onLongPress = vi.fn();
        const recognizer = createLongPressRecognizer(THRESHOLDS, timer, onLongPress);

        recognizer.press(1, 0, 0);
        recognizer.move(1, THRESHOLDS.slopPx, 0);
        harness().fire();

        expect(onLongPress).toHaveBeenCalled();
    });

    it("calls the press off on an early release and on a second finger", () => {
        const { timer, harness } = fakeTimer();
        const onLongPress = vi.fn();
        const recognizer = createLongPressRecognizer(THRESHOLDS, timer, onLongPress);

        recognizer.press(1, 0, 0);
        recognizer.release(1);
        harness().fire();
        recognizer.press(1, 0, 0);
        recognizer.press(2, 5, 5);
        harness().fire();

        expect(onLongPress).not.toHaveBeenCalled();
    });

    it("forgets that the last press fired once a new one begins", () => {
        const { timer, harness } = fakeTimer();
        const recognizer = createLongPressRecognizer(THRESHOLDS, timer, vi.fn());

        recognizer.press(1, 0, 0);
        harness().fire();
        recognizer.press(1, 0, 0);

        expect(recognizer.fired()).toBe(false);
    });
});
