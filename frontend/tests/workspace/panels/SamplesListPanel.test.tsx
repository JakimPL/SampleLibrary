import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as CloudApi from "../../../src/api/cloud";
import type * as SamplesApi from "../../../src/api/samples";
import { SamplesListPanel } from "../../../src/workspace/panels/SamplesListPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { listSamples, getSuggestionTags } = vi.hoisted(() => ({
    listSamples: vi.fn(),
    getSuggestionTags: vi.fn().mockResolvedValue([]),
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, listSamples };
});

vi.mock("../../../src/api/cloud", async () => {
    const actual = await vi.importActual<typeof CloudApi>("../../../src/api/cloud");
    return { ...actual, getSuggestionTags };
});

function renderPanel(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/"]}>
            <Routes>
                <Route path="/" element={<SamplesListPanel />} />
                <Route path="/samples/:sampleHash" element={<p>sample route</p>} />
            </Routes>
        </MemoryRouter>,
    );
}

const SAMPLE_SUMMARY = {
    hash: "abc",
    depth: 16,
    channels: 1,
    frames: 4096,
    occurrence_count: 3,
    display_name: "kick",
    suggested_label: null,
    hand_label: null,
    size_bytes: 8192,
    thumbnail: null,
    playback_rate_hz: null,
    equivalence_class_hash: null,
    equivalence_member_count: 1,
};

describe("SamplesListPanel", () => {
    it("shows a loading state before the samples arrive", () => {
        listSamples.mockReturnValue(new Promise(() => undefined));

        renderPanel();

        expect(screen.getByText("Loading…")).toBeInTheDocument();
    });

    it("renders the fetched samples once loaded", async () => {
        listSamples.mockResolvedValue({ items: [SAMPLE_SUMMARY], total: 1, limit: 50, offset: 0 });

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("link", { name: /kick/ })).toHaveAttribute("href", "/samples/abc");
        });
        expect(screen.getByText("3")).toBeInTheDocument();
    });

    it("groups samples by acoustic identity by default, folding the raw rows it pages through", async () => {
        listSamples.mockResolvedValue({ items: [SAMPLE_SUMMARY], total: 1, limit: 50, offset: 0 });

        renderPanel();

        await waitFor(() => {
            expect(screen.getByText(/1 of 1 loaded · 1 groups/)).toBeInTheDocument();
        });
        expect(listSamples).toHaveBeenCalledWith(expect.objectContaining({ groupByEquivalence: false }));
    });

    it("shows an error notice when the request fails", async () => {
        listSamples.mockRejectedValue(new Error("network down"));

        renderPanel();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("network down");
        });
    });

    it("highlights a sample in the shared selection store on a plain click", async () => {
        listSamples.mockResolvedValue({ items: [SAMPLE_SUMMARY], total: 1, limit: 50, offset: 0 });
        renderPanel();
        const row = await waitFor(() => screen.getByRole("row", { name: /kick/ }));

        fireEvent.click(row);

        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "abc" });
    });

    it("navigates to the sample's own route on a double-click", async () => {
        listSamples.mockResolvedValue({ items: [SAMPLE_SUMMARY], total: 1, limit: 50, offset: 0 });
        renderPanel();
        const row = await waitFor(() => screen.getByRole("row", { name: /kick/ }));

        fireEvent.doubleClick(row);

        expect(await screen.findByText("sample route")).toBeInTheDocument();
    });
});
