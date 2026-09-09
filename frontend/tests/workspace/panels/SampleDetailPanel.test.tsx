import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../src/api/client";
import type * as SamplesApi from "../../../src/api/samples";
import { SampleDetailPanel } from "../../../src/workspace/panels/SampleDetailPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { getSample, getSampleRelations, getSimilarSamples, getSampleDistance } = vi.hoisted(() => ({
    getSample: vi.fn(),
    getSampleRelations: vi.fn(),
    getSimilarSamples: vi.fn(),
    getSampleDistance: vi.fn(),
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples, getSampleDistance };
});

function renderPanel(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<SampleDetailPanel />} />
                <Route path="/modules/:moduleHash" element={<p>module route</p>} />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

const SAMPLE_DETAIL = {
    hash: "abc",
    depth: 16,
    channels: 1,
    frames: 4096,
    display_name: "kick",
    category: "kick",
    size_bytes: 8192,
    duration_seconds: 0.09,
    playback_rate_hz: 8363,
    occurrences: [
        {
            properties: {
                sample_hash: "abc",
                occurrence: { module_hash: "module-1", instrument_index: 0, sample_slot: 0 },
                name: "kick",
                rate: 8363,
                volume: 64,
                tracker: "xm",
                tuning: { relative_note: 0, finetune: 0 },
            },
            module: { hash: "module-1", title: "A Song", filename: "song.xm", tracker: "xm" },
        },
    ],
};

describe("SampleDetailPanel", () => {
    it("shows a placeholder when no sample is focused", () => {
        renderPanel();

        expect(screen.getByText(/No sample focused yet/)).toBeInTheDocument();
    });

    it("shows the focused sample's detail once loaded", async () => {
        getSample.mockResolvedValue(SAMPLE_DETAIL);
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("heading", { name: "kick" })).toBeInTheDocument();
        });
        expect(screen.getByRole("link", { name: "A Song" })).toHaveAttribute("href", "/modules/module-1");
        expect(screen.getByRole("heading", { name: "Similar Samples" })).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Frequently Co-occurs With" })).toBeInTheDocument();
    });

    it("renders the sample's spectral neighbors once they are loaded", async () => {
        getSample.mockResolvedValue(SAMPLE_DETAIL);
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([{ hash: "d".repeat(64), distance: 1.5 }]);
        useSelectionStore.getState().focusSample("abc");

        renderPanel();

        expect(await screen.findByText("dddddddd")).toBeInTheDocument();
        expect(screen.getByText("1.500")).toBeInTheDocument();
    });

    it("shows an honest empty state when the sample has no spectral neighbors yet", async () => {
        getSample.mockResolvedValue(SAMPLE_DETAIL);
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockRejectedValue(new ApiError(404, "not found"));
        useSelectionStore.getState().focusSample("abc");

        renderPanel();

        expect(await screen.findByText(/No spectral neighbors yet/)).toBeInTheDocument();
    });

    it("shows an error notice when the sample cannot be found", async () => {
        getSample.mockRejectedValue(new Error("no sample cataloged with hash 'abc'"));
        getSampleRelations.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("no sample cataloged with hash 'abc'");
        });
    });

    it("shows the spectral distance to a comparison sample and clears it on request", async () => {
        getSample.mockResolvedValue(SAMPLE_DETAIL);
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        getSampleDistance.mockResolvedValue({ sample_hash: "abc", other_hash: "def", distance: 2.5 });
        useSelectionStore.getState().focusSample("abc");
        useSelectionStore.getState().setComparisonSample("def");

        renderPanel();

        expect(await screen.findByText("distance 2.500")).toBeInTheDocument();
        expect(getSampleDistance).toHaveBeenCalledWith("abc", "def");

        fireEvent.click(screen.getByRole("button", { name: "Clear comparison" }));

        expect(useSelectionStore.getState().comparisonSampleHash).toBeNull();
    });

    it("highlights an occurrence's module row on a plain click and navigates to it on a double-click", async () => {
        getSample.mockResolvedValue(SAMPLE_DETAIL);
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");
        renderPanel();
        const row = await waitFor(() => screen.getByRole("row", { name: /A Song/ }));

        fireEvent.click(row);
        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "module", hash: "module-1" });

        fireEvent.doubleClick(row);
        expect(await screen.findByText("module route")).toBeInTheDocument();
    });
});
