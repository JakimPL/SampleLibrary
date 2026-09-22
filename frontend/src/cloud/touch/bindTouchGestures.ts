import type { TouchGestureRecognizer, TouchPoint } from "./touchGestures";

const MOUSE_POINTER_TYPE = "mouse";

export interface TouchBinding {
    readonly unbind: () => void;
    /** The kind of pointer that last pressed the canvas, which a trailing click is judged by. */
    readonly lastPointerType: () => string | null;
}

/**
 * Routes every pointer that is not a mouse through the recognizer, in the canvas's own coordinates.
 * Canceling the touch start and the pointer down keeps the browser's compatibility mouse events
 * away from the scatterplot, whose own handlers know only the mouse; the click a tap may still
 * raise is stopped at `container` before the canvas sees it, so a tap never doubles as a click.
 */
export function bindTouchGestures(
    canvas: HTMLCanvasElement,
    container: HTMLElement,
    recognizer: TouchGestureRecognizer,
): TouchBinding {
    let lastPointerType: string | null = null;

    function pointOf(event: PointerEvent): TouchPoint {
        const bounds = canvas.getBoundingClientRect();
        return { id: event.pointerId, x: event.clientX - bounds.left, y: event.clientY - bounds.top };
    }

    function handlePointerDown(event: PointerEvent): void {
        lastPointerType = event.pointerType;
        if (event.pointerType === MOUSE_POINTER_TYPE) {
            return;
        }
        event.preventDefault();
        canvas.setPointerCapture(event.pointerId);
        recognizer.press(pointOf(event));
    }

    function handlePointerMove(event: PointerEvent): void {
        if (event.pointerType !== MOUSE_POINTER_TYPE) {
            recognizer.move(pointOf(event));
        }
    }

    function handlePointerUp(event: PointerEvent): void {
        if (event.pointerType !== MOUSE_POINTER_TYPE) {
            recognizer.release(event.pointerId);
        }
    }

    function handlePointerCancel(event: PointerEvent): void {
        if (event.pointerType !== MOUSE_POINTER_TYPE) {
            recognizer.cancel();
        }
    }

    function handleTouchStart(event: TouchEvent): void {
        event.preventDefault();
    }

    function gateClick(event: MouseEvent): void {
        if (lastPointerType !== null && lastPointerType !== MOUSE_POINTER_TYPE) {
            event.stopPropagation();
            event.preventDefault();
        }
    }

    canvas.addEventListener("pointerdown", handlePointerDown);
    canvas.addEventListener("pointermove", handlePointerMove);
    canvas.addEventListener("pointerup", handlePointerUp);
    canvas.addEventListener("pointercancel", handlePointerCancel);
    canvas.addEventListener("touchstart", handleTouchStart, { passive: false });
    container.addEventListener("click", gateClick, true);
    container.addEventListener("dblclick", gateClick, true);

    return {
        unbind(): void {
            canvas.removeEventListener("pointerdown", handlePointerDown);
            canvas.removeEventListener("pointermove", handlePointerMove);
            canvas.removeEventListener("pointerup", handlePointerUp);
            canvas.removeEventListener("pointercancel", handlePointerCancel);
            canvas.removeEventListener("touchstart", handleTouchStart);
            container.removeEventListener("click", gateClick, true);
            container.removeEventListener("dblclick", gateClick, true);
        },
        lastPointerType: () => lastPointerType,
    };
}
