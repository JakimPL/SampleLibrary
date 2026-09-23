import type { MouseEvent } from "react";
import { useMemo, useRef } from "react";

import { createDoubleTapRecognizer } from "./doubleTap";
import { DOUBLE_TAP_INTERVAL_MS, KEYBOARD_CLICK_DETAIL, TAP_SLOP_PX } from "./gestureThresholds";

export interface DoubleTapHandlers {
    readonly onClick: (event: MouseEvent<HTMLElement>) => void;
}

/**
 * A click handler that calls `onDoubleTap` on the second of two taps in one place in quick
 * succession, counted from the clicks a finger or a mouse raises, and at once on the click a key
 * press raises, so a keyboard reaches the action in one stroke. A single tap is only remembered,
 * so the element waits for the second with nothing delayed.
 */
export function useDoubleTap(onDoubleTap: () => void): DoubleTapHandlers {
    const onDoubleTapRef = useRef(onDoubleTap);
    onDoubleTapRef.current = onDoubleTap;
    const recognizer = useMemo(
        () => createDoubleTapRecognizer({ intervalMs: DOUBLE_TAP_INTERVAL_MS, slopPx: TAP_SLOP_PX }),
        [],
    );

    return useMemo(
        () => ({
            onClick(event): void {
                if (
                    event.detail === KEYBOARD_CLICK_DETAIL ||
                    recognizer.tap(event.clientX, event.clientY, Date.now())
                ) {
                    onDoubleTapRef.current();
                }
            },
        }),
        [recognizer],
    );
}
