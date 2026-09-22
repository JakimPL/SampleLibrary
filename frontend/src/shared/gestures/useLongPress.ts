import type { MouseEvent, PointerEvent } from "react";
import { useMemo, useRef } from "react";

import { LONG_PRESS_HOLD_MS, TAP_SLOP_PX } from "./gestureThresholds";
import { createLongPressRecognizer, windowTimer } from "./longPress";

export interface LongPressHandlers {
    readonly onPointerDown: (event: PointerEvent<HTMLElement>) => void;
    readonly onPointerMove: (event: PointerEvent<HTMLElement>) => void;
    readonly onPointerUp: (event: PointerEvent<HTMLElement>) => void;
    readonly onPointerCancel: (event: PointerEvent<HTMLElement>) => void;
    /** Swallows the click a finger raises as it lifts after a hold, so the hold is the whole gesture. */
    readonly onClickCapture: (event: MouseEvent<HTMLElement>) => void;
}

const TOUCH_POINTER_TYPE = "touch";

/**
 * Pointer handlers that call `onLongPress` when a finger rests on the element for the hold time.
 * A mouse or a pen passes straight through, and so does everything while `enabled` is off, so an
 * element spreads these wherever it stands and only touch input answers to them.
 */
export function useLongPress(onLongPress: () => void, enabled: boolean): LongPressHandlers {
    const onLongPressRef = useRef(onLongPress);
    onLongPressRef.current = onLongPress;
    const recognizer = useMemo(
        () =>
            createLongPressRecognizer({ holdMs: LONG_PRESS_HOLD_MS, slopPx: TAP_SLOP_PX }, windowTimer, () => {
                onLongPressRef.current();
            }),
        [],
    );

    return useMemo(
        () => ({
            onPointerDown(event): void {
                if (enabled && event.pointerType === TOUCH_POINTER_TYPE) {
                    recognizer.press(event.pointerId, event.clientX, event.clientY);
                }
            },
            onPointerMove(event): void {
                recognizer.move(event.pointerId, event.clientX, event.clientY);
            },
            onPointerUp(event): void {
                recognizer.release(event.pointerId);
            },
            onPointerCancel(): void {
                recognizer.cancel();
            },
            onClickCapture(event): void {
                if (recognizer.fired()) {
                    event.preventDefault();
                    event.stopPropagation();
                }
            },
        }),
        [enabled, recognizer],
    );
}
