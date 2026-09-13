import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MorphLink } from "../../src/cloud/MorphLink";

const FIRST = [10, 20] as const;
const SECOND = [110, 20] as const;

interface RenderOverrides {
    readonly weight?: number;
    readonly onWeightChange?: (weight: number) => void;
    readonly onWeightCommit?: () => void;
    readonly onDragChange?: (dragging: boolean) => void;
}

function renderLink(overrides: RenderOverrides = {}): HTMLElement {
    render(
        <MorphLink
            first={FIRST}
            second={SECOND}
            weight={overrides.weight ?? 0.5}
            onWeightChange={overrides.onWeightChange ?? vi.fn()}
            onWeightCommit={overrides.onWeightCommit ?? vi.fn()}
            onDragChange={overrides.onDragChange ?? vi.fn()}
        />,
    );
    return screen.getByRole("slider", { name: "Morph weight" });
}

describe("MorphLink", () => {
    it("places the marker along the line at the weight", () => {
        const marker = renderLink({ weight: 0.25 });

        expect(marker.style.left).toBe("35px");
        expect(marker.style.top).toBe("20px");
        expect(marker).toHaveAttribute("aria-valuenow", "0.25");
    });

    it("reports the snapped weight while the marker is dragged, and a commit on release", () => {
        const onWeightChange = vi.fn();
        const onWeightCommit = vi.fn();
        const onDragChange = vi.fn();
        const marker = renderLink({ onWeightChange, onWeightCommit, onDragChange });

        fireEvent.pointerDown(marker, { pointerId: 1, clientX: 60, clientY: 20 });
        fireEvent.pointerMove(marker, { pointerId: 1, clientX: 87, clientY: 45 });
        fireEvent.pointerUp(marker, { pointerId: 1, clientX: 87, clientY: 45 });

        expect(onWeightChange).toHaveBeenCalledWith(0.75);
        expect(onWeightCommit).toHaveBeenCalledTimes(1);
        expect(onDragChange.mock.calls).toEqual([[true], [false]]);
    });

    it("ignores a move that no press started", () => {
        const onWeightChange = vi.fn();
        const marker = renderLink({ onWeightChange });

        fireEvent.pointerMove(marker, { pointerId: 1, clientX: 87, clientY: 20 });

        expect(onWeightChange).not.toHaveBeenCalled();
    });

    it("nudges the weight by one step from the keyboard and commits on key release", () => {
        const onWeightChange = vi.fn();
        const onWeightCommit = vi.fn();
        const marker = renderLink({ weight: 0.5, onWeightChange, onWeightCommit });

        fireEvent.keyDown(marker, { key: "ArrowRight" });
        fireEvent.keyUp(marker, { key: "ArrowRight" });
        fireEvent.keyDown(marker, { key: "Home" });
        fireEvent.keyDown(marker, { key: "End" });
        fireEvent.keyDown(marker, { key: "Tab" });

        expect(onWeightChange.mock.calls).toEqual([[0.5625], [0], [1]]);
        expect(onWeightCommit).toHaveBeenCalledTimes(1);
    });
});
