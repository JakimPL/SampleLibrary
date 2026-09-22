import { fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { bindTouchGestures } from "../../../src/cloud/touch/bindTouchGestures";
import type { TouchGestureRecognizer } from "../../../src/cloud/touch/touchGestures";

function fakeRecognizer(): { readonly [Key in keyof TouchGestureRecognizer]: ReturnType<typeof vi.fn> } {
    return { press: vi.fn(), move: vi.fn(), release: vi.fn(), cancel: vi.fn(), state: vi.fn(() => "idle") };
}

function mountCanvas(): { readonly canvas: HTMLCanvasElement; readonly container: HTMLDivElement } {
    const container = document.createElement("div");
    const canvas = document.createElement("canvas");
    container.append(canvas);
    document.body.append(container);
    return { canvas, container };
}

describe("bindTouchGestures", () => {
    it("feeds a finger's presses, moves and lifts to the recognizer in the canvas's coordinates", () => {
        const { canvas, container } = mountCanvas();
        const recognizer = fakeRecognizer();
        const pairsFrom = vi.fn(() => true);
        bindTouchGestures(canvas, container, recognizer, { pairsFrom });

        fireEvent.pointerDown(canvas, { pointerId: 7, pointerType: "touch", clientX: 30, clientY: 40 });
        fireEvent.pointerMove(canvas, { pointerId: 7, pointerType: "touch", clientX: 50, clientY: 40 });
        fireEvent.pointerUp(canvas, { pointerId: 7, pointerType: "touch", clientX: 50, clientY: 40 });

        expect(recognizer.press).toHaveBeenCalledWith({ id: 7, x: 30, y: 40 }, true);
        expect(pairsFrom).toHaveBeenCalledWith(30, 40);
        expect(recognizer.move).toHaveBeenCalledWith({ id: 7, x: 50, y: 40 });
        expect(recognizer.release).toHaveBeenCalledWith(7);
    });

    it("leaves a mouse to the scatterplot's own handlers", () => {
        const { canvas, container } = mountCanvas();
        const recognizer = fakeRecognizer();
        bindTouchGestures(canvas, container, recognizer, { pairsFrom: () => false });

        const down = fireEvent.pointerDown(canvas, { pointerId: 1, pointerType: "mouse", clientX: 30, clientY: 40 });
        fireEvent.pointerUp(canvas, { pointerId: 1, pointerType: "mouse", clientX: 30, clientY: 40 });

        expect(down).toBe(true);
        expect(recognizer.press).not.toHaveBeenCalled();
        expect(recognizer.release).not.toHaveBeenCalled();
    });

    it("cancels the browser's own handling of a touch and stops the click a tap raises", () => {
        const { canvas, container } = mountCanvas();
        const recognizer = fakeRecognizer();
        bindTouchGestures(canvas, container, recognizer, { pairsFrom: () => false });
        const canvasClick = vi.fn();
        canvas.addEventListener("click", canvasClick);

        const touchStart = fireEvent.touchStart(canvas);
        const pointerDown = fireEvent.pointerDown(canvas, { pointerId: 2, pointerType: "touch" });
        fireEvent.pointerUp(canvas, { pointerId: 2, pointerType: "touch" });
        fireEvent.click(canvas);

        expect(touchStart).toBe(false);
        expect(pointerDown).toBe(false);
        expect(canvasClick).not.toHaveBeenCalled();
    });

    it("lets a click through again once a mouse pressed last", () => {
        const { canvas, container } = mountCanvas();
        bindTouchGestures(canvas, container, fakeRecognizer(), { pairsFrom: () => false });
        const canvasClick = vi.fn();
        canvas.addEventListener("click", canvasClick);

        fireEvent.pointerDown(canvas, { pointerId: 2, pointerType: "touch" });
        fireEvent.pointerDown(canvas, { pointerId: 1, pointerType: "mouse" });
        fireEvent.click(canvas);

        expect(canvasClick).toHaveBeenCalledTimes(1);
    });

    it("cancels the recognizer when the pointer is canceled, and listens no more once unbound", () => {
        const { canvas, container } = mountCanvas();
        const recognizer = fakeRecognizer();
        const binding = bindTouchGestures(canvas, container, recognizer, { pairsFrom: () => false });

        fireEvent.pointerCancel(canvas, { pointerId: 2, pointerType: "touch" });
        expect(recognizer.cancel).toHaveBeenCalledTimes(1);

        binding.unbind();
        fireEvent.pointerDown(canvas, { pointerId: 3, pointerType: "touch" });
        expect(recognizer.press).not.toHaveBeenCalled();
    });
});
