export interface DoubleTapThresholds {
    /** How long after one tap a second still pairs with it. */
    readonly intervalMs: number;
    /** How far from the first tap a second may land and still pair with it. */
    readonly slopPx: number;
}

export interface DoubleTapRecognizer {
    /** Reports a tap at a point and a time, and whether it completes a double tap. */
    readonly tap: (x: number, y: number, atMs: number) => boolean;
}

interface Tap {
    readonly x: number;
    readonly y: number;
    readonly atMs: number;
}

/**
 * Recognizes two taps in one place in quick succession: a tap within the interval and the slop of
 * the one before completes the pair, which is then spent, so a third tap begins a new pair. Every
 * other tap is remembered as a possible first. The taps are counted by hand, which is what reaches
 * a finger's double tap on a phone.
 */
export function createDoubleTapRecognizer(thresholds: DoubleTapThresholds): DoubleTapRecognizer {
    let previous: Tap | null = null;

    function pairsWithPrevious(tap: Tap): boolean {
        return (
            previous !== null &&
            tap.atMs - previous.atMs <= thresholds.intervalMs &&
            Math.hypot(tap.x - previous.x, tap.y - previous.y) <= thresholds.slopPx
        );
    }

    return {
        tap(x, y, atMs): boolean {
            const tap = { x, y, atMs };
            if (pairsWithPrevious(tap)) {
                previous = null;
                return true;
            }
            previous = tap;
            return false;
        },
    };
}
