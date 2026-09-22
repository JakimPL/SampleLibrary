export interface LongPressThresholds {
    readonly holdMs: number;
    readonly slopPx: number;
}

/** Schedules `fire` after `delayMs` and hands back the way to call it off. */
export type LongPressTimer = (fire: () => void, delayMs: number) => () => void;

export interface LongPressRecognizer {
    readonly press: (pointerId: number, x: number, y: number) => void;
    readonly move: (pointerId: number, x: number, y: number) => void;
    readonly release: (pointerId: number) => void;
    readonly cancel: () => void;
    /** Whether the press now ending fired, which its trailing click should honor by doing nothing. */
    readonly fired: () => boolean;
}

interface Press {
    readonly pointerId: number;
    readonly x: number;
    readonly y: number;
    readonly callOff: () => void;
}

/** Schedules through the window's own timer. */
export const windowTimer: LongPressTimer = (fire, delayMs) => {
    const handle = window.setTimeout(fire, delayMs);
    return (): void => {
        window.clearTimeout(handle);
    };
};

/**
 * Recognizes a finger resting in one place: a press that stays within the slop for the hold time
 * fires `onLongPress` once, at the point pressed. Movement past the slop, a second pointer, or an
 * early release call it off. The recognizer keeps saying that the last press fired until the next
 * one begins, so the click a browser raises when the finger lifts can be told from a tap.
 */
export function createLongPressRecognizer(
    thresholds: LongPressThresholds,
    timer: LongPressTimer,
    onLongPress: (x: number, y: number) => void,
): LongPressRecognizer {
    let press: Press | null = null;
    let fired = false;

    function callOff(): void {
        press?.callOff();
        press = null;
    }

    return {
        press(pointerId, x, y): void {
            if (press !== null) {
                callOff();
                return;
            }
            fired = false;
            const stop = timer(() => {
                fired = true;
                press = null;
                onLongPress(x, y);
            }, thresholds.holdMs);
            press = { pointerId, x, y, callOff: stop };
        },
        move(pointerId, x, y): void {
            if (press?.pointerId !== pointerId) {
                return;
            }
            if (Math.hypot(x - press.x, y - press.y) > thresholds.slopPx) {
                callOff();
            }
        },
        release(pointerId): void {
            if (press?.pointerId === pointerId) {
                callOff();
            }
        },
        cancel: callOff,
        fired: () => fired,
    };
}
