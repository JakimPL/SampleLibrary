import type { LongPressTimer } from "../../shared/gestures/longPress";

export interface TouchPoint {
    readonly id: number;
    readonly x: number;
    readonly y: number;
}

export interface TouchGestureThresholds {
    readonly tapSlopPx: number;
    readonly holdMs: number;
    readonly pinchMinimumDistancePx: number;
}

/** What the fingers on the cloud amount to, reported as each gesture resolves. */
export interface TouchGestureListener {
    readonly onTap: (x: number, y: number) => void;
    readonly onLongPress: (x: number, y: number) => void;
    readonly onPan: (dxPx: number, dyPx: number) => void;
    /** A spread or squeeze by `factor` about the fingers' midpoint, which itself drifted by `dxPx`, `dyPx`. */
    readonly onPinch: (factor: number, centerX: number, centerY: number, dxPx: number, dyPx: number) => void;
    readonly onPairDrag: (x: number, y: number) => void;
    readonly onPairRelease: (x: number, y: number) => void;
    readonly onCancel: () => void;
}

export type TouchGestureState = "idle" | "pressing" | "panning" | "pinching" | "held" | "pairing";

export interface TouchGestureRecognizer {
    /** A finger landing; `pairs` says a drag from here builds a pair rather than panning the view. */
    readonly press: (point: TouchPoint, pairs: boolean) => void;
    readonly move: (point: TouchPoint) => void;
    readonly release: (id: number) => void;
    readonly cancel: () => void;
    readonly state: () => TouchGestureState;
}

interface Press {
    readonly origin: TouchPoint;
    readonly pairs: boolean;
    readonly callOffHold: () => void;
}

interface Pinch {
    readonly distance: number;
    readonly center: readonly [number, number];
}

const HALF = 0.5;
const PINCH_FINGER_COUNT = 2;

function distanceBetween(first: TouchPoint, second: TouchPoint): number {
    return Math.hypot(second.x - first.x, second.y - first.y);
}

function midpointOf(first: TouchPoint, second: TouchPoint): readonly [number, number] {
    return [(first.x + second.x) * HALF, (first.y + second.y) * HALF];
}

/**
 * Reads the fingers on the cloud as gestures, from the pointer events alone and with a timer
 * handed in, so every path can be walked in a test.
 *
 * One finger that lifts within the slop is a tap; one that rests for the hold time is a long press,
 * after which nothing else happens until it lifts; one that moves past the slop pans, or drags a
 * pair when its press said so. A second finger turns a press or a pan into a pinch, reported as a
 * factor about the fingers' midpoint together with the midpoint's own drift; when one of them
 * lifts, the other goes on panning. A cancel drops everything.
 */
export function createTouchGestureRecognizer(
    thresholds: TouchGestureThresholds,
    timer: LongPressTimer,
    listener: TouchGestureListener,
): TouchGestureRecognizer {
    let state: TouchGestureState = "idle";
    const fingers = new Map<number, TouchPoint>();
    let press: Press | null = null;
    let last: TouchPoint | null = null;
    let pinch: Pinch | null = null;

    function reset(): void {
        press?.callOffHold();
        press = null;
        last = null;
        pinch = null;
        fingers.clear();
        state = "idle";
    }

    function twoFingers(): readonly [TouchPoint, TouchPoint] | null {
        const [first, second] = [...fingers.values()];
        return first !== undefined && second !== undefined ? [first, second] : null;
    }

    function beginPinch(): void {
        const pair = twoFingers();
        if (pair === null) {
            return;
        }
        press?.callOffHold();
        press = null;
        pinch = { distance: distanceBetween(pair[0], pair[1]), center: midpointOf(pair[0], pair[1]) };
        state = "pinching";
    }

    function continuePinch(): void {
        const pair = twoFingers();
        if (pair === null || pinch === null) {
            return;
        }
        const distance = distanceBetween(pair[0], pair[1]);
        const center = midpointOf(pair[0], pair[1]);
        const factor =
            distance >= thresholds.pinchMinimumDistancePx && pinch.distance >= thresholds.pinchMinimumDistancePx
                ? distance / pinch.distance
                : 1;
        listener.onPinch(factor, center[0], center[1], center[0] - pinch.center[0], center[1] - pinch.center[1]);
        pinch = { distance, center };
    }

    function movePressing(point: TouchPoint): void {
        if (press === null || Math.hypot(point.x - press.origin.x, point.y - press.origin.y) <= thresholds.tapSlopPx) {
            return;
        }
        const { origin, pairs } = press;
        press.callOffHold();
        press = null;
        if (pairs) {
            state = "pairing";
            listener.onPairDrag(point.x, point.y);
            return;
        }
        state = "panning";
        last = point;
        listener.onPan(point.x - origin.x, point.y - origin.y);
    }

    function movePanning(point: TouchPoint): void {
        if (last?.id !== point.id) {
            return;
        }
        listener.onPan(point.x - last.x, point.y - last.y);
        last = point;
    }

    return {
        press(point, pairs): void {
            fingers.set(point.id, point);
            if (state === "idle") {
                const callOffHold = timer(() => {
                    if (state === "pressing" && press !== null) {
                        const { origin } = press;
                        press = null;
                        state = "held";
                        listener.onLongPress(origin.x, origin.y);
                    }
                }, thresholds.holdMs);
                press = { origin: point, pairs, callOffHold };
                state = "pressing";
                return;
            }
            if ((state === "pressing" || state === "panning") && fingers.size === PINCH_FINGER_COUNT) {
                beginPinch();
            }
        },
        move(point): void {
            if (!fingers.has(point.id)) {
                return;
            }
            fingers.set(point.id, point);
            switch (state) {
                case "pressing":
                    movePressing(point);
                    break;
                case "panning":
                    movePanning(point);
                    break;
                case "pinching":
                    continuePinch();
                    break;
                case "pairing":
                    listener.onPairDrag(point.x, point.y);
                    break;
                case "held":
                case "idle":
                    break;
            }
        },
        release(id): void {
            const point = fingers.get(id);
            if (point === undefined) {
                return;
            }
            fingers.delete(id);
            switch (state) {
                case "pressing": {
                    const origin = press?.origin ?? point;
                    reset();
                    listener.onTap(origin.x, origin.y);
                    break;
                }
                case "pairing":
                    reset();
                    listener.onPairRelease(point.x, point.y);
                    break;
                case "pinching": {
                    const remaining = [...fingers.values()][0];
                    if (remaining === undefined) {
                        reset();
                    } else {
                        pinch = null;
                        last = remaining;
                        state = "panning";
                    }
                    break;
                }
                case "panning":
                case "held":
                case "idle":
                    if (fingers.size === 0) {
                        reset();
                    }
                    break;
            }
        },
        cancel(): void {
            const wasActive = state !== "idle";
            reset();
            if (wasActive) {
                listener.onCancel();
            }
        },
        state: () => state,
    };
}
