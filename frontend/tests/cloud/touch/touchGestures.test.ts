import { describe, expect, it, vi } from "vitest";

import {
    createTouchGestureRecognizer,
    type TouchGestureListener,
    type TouchGestureRecognizer,
} from "../../../src/cloud/touch/touchGestures";
import type { LongPressTimer } from "../../../src/shared/gestures/longPress";

const THRESHOLDS = { tapSlopPx: 10, holdMs: 500, pinchMinimumDistancePx: 8 };

interface Harness {
    readonly recognizer: TouchGestureRecognizer;
    readonly listener: { readonly [Key in keyof TouchGestureListener]: ReturnType<typeof vi.fn> };
    /** Fires the pending hold, as the timer would after the hold time. */
    readonly elapseHold: () => void;
}

function harness(): Harness {
    let pendingHold: (() => void) | null = null;
    const timer: LongPressTimer = (fire) => {
        pendingHold = fire;
        return (): void => {
            pendingHold = null;
        };
    };
    const listener = {
        onTap: vi.fn(),
        onLongPress: vi.fn(),
        onPan: vi.fn(),
        onPinch: vi.fn(),
        onPairDrag: vi.fn(),
        onPairRelease: vi.fn(),
        onCancel: vi.fn(),
    };
    return {
        recognizer: createTouchGestureRecognizer(THRESHOLDS, timer, listener),
        listener,
        elapseHold: (): void => {
            pendingHold?.();
        },
    };
}

describe("createTouchGestureRecognizer", () => {
    it("reads a finger that lifts within the slop as a tap at the point pressed", () => {
        const { recognizer, listener } = harness();

        recognizer.press({ id: 1, x: 100, y: 100 }, false);
        recognizer.move({ id: 1, x: 104, y: 103 });
        recognizer.release(1);

        expect(listener.onTap).toHaveBeenCalledWith(100, 100);
        expect(listener.onPan).not.toHaveBeenCalled();
        expect(recognizer.state()).toBe("idle");
    });

    it("reads a finger that rests for the hold time as a long press, and nothing more until it lifts", () => {
        const { recognizer, listener, elapseHold } = harness();

        recognizer.press({ id: 1, x: 40, y: 50 }, false);
        elapseHold();
        recognizer.move({ id: 1, x: 90, y: 50 });
        recognizer.release(1);

        expect(listener.onLongPress).toHaveBeenCalledWith(40, 50);
        expect(listener.onPan).not.toHaveBeenCalled();
        expect(listener.onTap).not.toHaveBeenCalled();
        expect(recognizer.state()).toBe("idle");
    });

    it("pans once a finger moves past the slop, by each move's distance", () => {
        const { recognizer, listener, elapseHold } = harness();

        recognizer.press({ id: 1, x: 100, y: 100 }, false);
        recognizer.move({ id: 1, x: 130, y: 100 });
        recognizer.move({ id: 1, x: 140, y: 120 });
        elapseHold();
        recognizer.release(1);

        expect(listener.onPan).toHaveBeenNthCalledWith(1, 30, 0);
        expect(listener.onPan).toHaveBeenNthCalledWith(2, 10, 20);
        expect(listener.onLongPress).not.toHaveBeenCalled();
        expect(listener.onTap).not.toHaveBeenCalled();
    });

    it("pinches with two fingers, by the spread's factor about their drifting midpoint", () => {
        const { recognizer, listener } = harness();

        recognizer.press({ id: 1, x: 200, y: 300 }, false);
        recognizer.press({ id: 2, x: 300, y: 300 }, false);
        expect(recognizer.state()).toBe("pinching");
        recognizer.move({ id: 2, x: 400, y: 320 });

        expect(listener.onPinch).toHaveBeenCalledTimes(1);
        const [factor, centerX, centerY, driftX, driftY] = listener.onPinch.mock.calls[0] as number[];
        expect(factor).toBeCloseTo(Math.hypot(200, 20) / 100, 5);
        expect(centerX).toBe(300);
        expect(centerY).toBe(310);
        expect(driftX).toBe(50);
        expect(driftY).toBe(10);
    });

    it("goes on panning with the finger left once the other lifts", () => {
        const { recognizer, listener } = harness();
        recognizer.press({ id: 1, x: 200, y: 300 }, false);
        recognizer.press({ id: 2, x: 300, y: 300 }, false);

        recognizer.release(2);
        recognizer.move({ id: 1, x: 210, y: 305 });
        recognizer.release(1);

        expect(listener.onPan).toHaveBeenCalledWith(10, 5);
        expect(listener.onTap).not.toHaveBeenCalled();
        expect(recognizer.state()).toBe("idle");
    });

    it("drags a pair from a press that said so, and releases it where the finger lifts", () => {
        const { recognizer, listener } = harness();

        recognizer.press({ id: 1, x: 10, y: 10 }, true);
        recognizer.move({ id: 1, x: 60, y: 80 });
        recognizer.move({ id: 1, x: 70, y: 90 });
        recognizer.release(1);

        expect(listener.onPairDrag).toHaveBeenCalledWith(60, 80);
        expect(listener.onPairDrag).toHaveBeenLastCalledWith(70, 90);
        expect(listener.onPairRelease).toHaveBeenCalledWith(70, 90);
        expect(listener.onPan).not.toHaveBeenCalled();
    });

    it("still reads a pairing press that stays put as a tap", () => {
        const { recognizer, listener } = harness();

        recognizer.press({ id: 1, x: 10, y: 10 }, true);
        recognizer.release(1);

        expect(listener.onTap).toHaveBeenCalledWith(10, 10);
        expect(listener.onPairRelease).not.toHaveBeenCalled();
    });

    it("drops everything on a cancel and says so", () => {
        const { recognizer, listener, elapseHold } = harness();
        recognizer.press({ id: 1, x: 10, y: 10 }, false);

        recognizer.cancel();
        elapseHold();

        expect(listener.onCancel).toHaveBeenCalledTimes(1);
        expect(listener.onLongPress).not.toHaveBeenCalled();
        expect(recognizer.state()).toBe("idle");
    });
});
