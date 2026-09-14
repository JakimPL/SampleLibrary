import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { MarkerAppearance } from "../../src/cloud/markerGeometry";
import { MorphLink } from "../../src/cloud/MorphLink";

const FIRST = [10, 20] as const;
const SECOND = [110, 20] as const;
const ROUND: MarkerAppearance = {
    shape: "circle",
    sizePx: 13,
    lineWidthPx: 1.5,
    casingWidthPx: 1.5,
    devicePixelRatio: 1,
};
const SQUARE: MarkerAppearance = {
    shape: "square",
    sizePx: 7,
    lineWidthPx: 1,
    casingWidthPx: 0,
    devicePixelRatio: 1.75,
};

interface RenderOverrides {
    readonly weight?: number;
    readonly appearance?: MarkerAppearance;
    readonly onWeightChange?: (weight: number) => void;
    readonly onWeightCommit?: () => void;
    readonly onDragChange?: (dragging: boolean) => void;
}

function renderLink(overrides: RenderOverrides = {}): {
    readonly marker: HTMLElement;
    readonly container: HTMLElement;
} {
    const { container } = render(
        <MorphLink
            first={FIRST}
            second={SECOND}
            weight={overrides.weight ?? 0.5}
            appearance={overrides.appearance ?? ROUND}
            onWeightChange={overrides.onWeightChange ?? vi.fn()}
            onWeightCommit={overrides.onWeightCommit ?? vi.fn()}
            onDragChange={overrides.onDragChange ?? vi.fn()}
        />,
    );
    return { marker: screen.getByRole("slider", { name: "Morph weight" }), container };
}

describe("MorphLink", () => {
    it("places the marker along the line at the weight", () => {
        const { marker } = renderLink({ weight: 0.25 });

        expect(marker.style.left).toBe("35px");
        expect(marker.style.top).toBe("20px");
        expect(marker).toHaveAttribute("aria-valuenow", "0.25");
    });

    it("reports the snapped weight while the marker is dragged, and a commit on release", () => {
        const onWeightChange = vi.fn();
        const onWeightCommit = vi.fn();
        const onDragChange = vi.fn();
        const { marker } = renderLink({ onWeightChange, onWeightCommit, onDragChange });

        fireEvent.pointerDown(marker, { pointerId: 1, clientX: 60, clientY: 20 });
        fireEvent.pointerMove(marker, { pointerId: 1, clientX: 87, clientY: 45 });
        fireEvent.pointerUp(marker, { pointerId: 1, clientX: 87, clientY: 45 });

        expect(onWeightChange).toHaveBeenCalledWith(0.75);
        expect(onWeightCommit).toHaveBeenCalledTimes(1);
        expect(onDragChange.mock.calls).toEqual([[true], [false]]);
    });

    it("ignores a move that no press started", () => {
        const onWeightChange = vi.fn();
        const { marker } = renderLink({ onWeightChange });

        fireEvent.pointerMove(marker, { pointerId: 1, clientX: 87, clientY: 20 });

        expect(onWeightChange).not.toHaveBeenCalled();
    });

    it("nudges the weight by one step from the keyboard and commits on key release", () => {
        const onWeightChange = vi.fn();
        const onWeightCommit = vi.fn();
        const { marker } = renderLink({ weight: 0.5, onWeightChange, onWeightCommit });

        fireEvent.keyDown(marker, { key: "ArrowRight" });
        fireEvent.keyUp(marker, { key: "ArrowRight" });
        fireEvent.keyDown(marker, { key: "Home" });
        fireEvent.keyDown(marker, { key: "End" });
        fireEvent.keyDown(marker, { key: "Tab" });

        expect(onWeightChange.mock.calls).toEqual([[0.5625], [0], [1]]);
        expect(onWeightCommit).toHaveBeenCalledTimes(1);
    });

    it("marks both ends as rings under round points", () => {
        const { container } = renderLink();

        expect(container.querySelectorAll(".morph-link-end circle.cloud-marker-stroke")).toHaveLength(2);
        expect(container.querySelector(".morph-link-node")).not.toBeInTheDocument();
    });

    it("draws the weight as a square node on whole device pixels under square points, lit while dragged", () => {
        const { marker, container } = renderLink({ weight: 0.25, appearance: SQUARE });

        const snapped = Math.round(35 * SQUARE.devicePixelRatio) / SQUARE.devicePixelRatio;
        expect(marker.style.left).toBe(`${String(snapped)}px`);
        expect(container.querySelectorAll(".morph-link-end rect.cloud-marker-stroke")).toHaveLength(2);
        expect(container.querySelector(".morph-link-node rect.cloud-marker-filled")).toBeInTheDocument();
        expect(container.querySelector(".morph-link-node-dragging")).not.toBeInTheDocument();

        fireEvent.pointerDown(marker, { pointerId: 1, clientX: 35, clientY: 20 });

        expect(container.querySelector(".morph-link-node-dragging")).toBeInTheDocument();
    });
});
