import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../../src/api/samples";
import { SpectralDistanceReadout } from "../../../src/workspace/panels/SpectralDistanceReadout";
import { INITIAL_SELECTION_STATE, useSelectionStore } from "../../../src/workspace/selectionStore";

const { getSampleDistance } = vi.hoisted(() => ({ getSampleDistance: vi.fn() }));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSampleDistance };
});

function resetSelection(): void {
    useSelectionStore.setState(INITIAL_SELECTION_STATE);
}

describe("SpectralDistanceReadout", () => {
    it("renders nothing when no sample is focused", () => {
        resetSelection();
        useSelectionStore.getState().setComparisonSample("def");

        const { container } = render(<SpectralDistanceReadout />);

        expect(container).toBeEmptyDOMElement();
    });

    it("renders nothing when no comparison sample is set", () => {
        resetSelection();
        useSelectionStore.getState().focusSample("abc");

        const { container } = render(<SpectralDistanceReadout />);

        expect(container).toBeEmptyDOMElement();
    });

    it("shows a loading state while the distance request is in flight", () => {
        resetSelection();
        useSelectionStore.getState().focusSample("abc");
        useSelectionStore.getState().setComparisonSample("def");
        getSampleDistance.mockReturnValue(new Promise(() => undefined));

        render(<SpectralDistanceReadout />);

        expect(screen.getByText("Computing distance…")).toBeInTheDocument();
    });

    it("shows the resolved distance between the focused and comparison samples", async () => {
        resetSelection();
        useSelectionStore.getState().focusSample("abc");
        useSelectionStore.getState().setComparisonSample("def");
        getSampleDistance.mockResolvedValue({ sample_hash: "abc", other_hash: "def", distance: 1.23456 });

        render(<SpectralDistanceReadout />);

        expect(await screen.findByText("distance 1.235")).toBeInTheDocument();
        expect(getSampleDistance).toHaveBeenCalledWith("abc", "def");
    });

    it("shows an error notice when the distance request fails", async () => {
        resetSelection();
        useSelectionStore.getState().focusSample("abc");
        useSelectionStore.getState().setComparisonSample("def");
        getSampleDistance.mockRejectedValue(new Error("no vector yet"));

        render(<SpectralDistanceReadout />);

        expect(await screen.findByText("no vector yet")).toBeInTheDocument();
    });

    it("clears the comparison sample when Clear comparison is clicked", async () => {
        resetSelection();
        useSelectionStore.getState().focusSample("abc");
        useSelectionStore.getState().setComparisonSample("def");
        getSampleDistance.mockResolvedValue({ sample_hash: "abc", other_hash: "def", distance: 1.0 });
        render(<SpectralDistanceReadout />);
        await waitFor(() => {
            expect(screen.getByRole("button", { name: "Clear comparison" })).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole("button", { name: "Clear comparison" }));

        expect(useSelectionStore.getState().comparisonSampleHash).toBeNull();
    });
});
