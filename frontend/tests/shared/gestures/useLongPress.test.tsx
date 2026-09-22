import { act, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LONG_PRESS_HOLD_MS } from "../../../src/shared/gestures/gestureThresholds";
import { useLongPress } from "../../../src/shared/gestures/useLongPress";

interface HeldProps {
    readonly enabled: boolean;
    readonly onLongPress: () => void;
    readonly onClick: () => void;
}

function Held({ enabled, onLongPress, onClick }: HeldProps): ReactElement {
    const handlers = useLongPress(onLongPress, enabled);
    return (
        <div onClick={onClick} role="presentation">
            <div {...handlers} role="presentation">
                held
            </div>
        </div>
    );
}

function press(pointerType: string): HTMLElement {
    const element = screen.getByText("held");
    fireEvent.pointerDown(element, { pointerId: 1, pointerType, clientX: 10, clientY: 10 });
    return element;
}

describe("useLongPress", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    afterEach(() => {
        vi.useRealTimers();
    });

    it("fires for a finger resting the hold time, and swallows the click that follows", () => {
        const onLongPress = vi.fn();
        const onClick = vi.fn();
        render(<Held enabled onLongPress={onLongPress} onClick={onClick} />);

        const element = press("touch");
        act(() => {
            vi.advanceTimersByTime(LONG_PRESS_HOLD_MS);
        });
        fireEvent.pointerUp(element, { pointerId: 1, pointerType: "touch" });
        fireEvent.click(element);

        expect(onLongPress).toHaveBeenCalledTimes(1);
        expect(onClick).not.toHaveBeenCalled();
    });

    it("lets a tap's click through", () => {
        const onLongPress = vi.fn();
        const onClick = vi.fn();
        render(<Held enabled onLongPress={onLongPress} onClick={onClick} />);

        const element = press("touch");
        fireEvent.pointerUp(element, { pointerId: 1, pointerType: "touch" });
        act(() => {
            vi.advanceTimersByTime(LONG_PRESS_HOLD_MS);
        });
        fireEvent.click(element);

        expect(onLongPress).not.toHaveBeenCalled();
        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it("ignores a mouse, and everything while disabled", () => {
        const onLongPress = vi.fn();
        const { rerender } = render(<Held enabled onLongPress={onLongPress} onClick={vi.fn()} />);

        press("mouse");
        act(() => {
            vi.advanceTimersByTime(LONG_PRESS_HOLD_MS);
        });
        rerender(<Held enabled={false} onLongPress={onLongPress} onClick={vi.fn()} />);
        press("touch");
        act(() => {
            vi.advanceTimersByTime(LONG_PRESS_HOLD_MS);
        });

        expect(onLongPress).not.toHaveBeenCalled();
    });
});
