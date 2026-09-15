import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { ApiError } from "../../../src/api/client";
import type * as SamplesApi from "../../../src/api/samples";
import { SampleDetailPanel } from "../../../src/workspace/panels/SampleDetailPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { getSample, getSampleRelations, getSimilarSamples } = vi.hoisted(() => ({
    getSample: vi.fn(),
    getSampleRelations: vi.fn(),
    getSimilarSamples: vi.fn(),
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples };
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
    suggested_labels: [],
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
    files: [],
};

describe("SampleDetailPanel", () => {
    it("shows a placeholder when no sample is focused", () => {
        renderPanel();

        expect(screen.getByText(/No sample selected yet/)).toBeInTheDocument();
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
        expect(screen.getByRole("button", { name: "Occurrences (1)" })).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByRole("button", { name: "Similar (0)" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Co-occurs" })).toBeInTheDocument();
    });

    it("lists the sample files a sample was found in beside its module slots, marking a file gone since its scan", async () => {
        getSample.mockResolvedValue({
            ...SAMPLE_DETAIL,
            occurrences: [],
            files: [
                { location: { directory: "/packs", relative_path: "Kicks/Kick 01.wav" }, rate: 44100, available: true },
                {
                    location: { directory: "/packs", relative_path: "Kicks/Kick 02.wav" },
                    rate: 44100,
                    available: false,
                },
            ],
        });
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");

        renderPanel();

        expect(await screen.findByRole("button", { name: "Occurrences (2)" })).toHaveAttribute("aria-pressed", "true");
        expect(screen.getByText("Kicks/Kick 01.wav")).toBeInTheDocument();
        expect(screen.getAllByText("unavailable")).toHaveLength(1);
        expect(screen.queryByRole("link", { name: "A Song" })).not.toBeInTheDocument();
    });

    it("renders the sample's spectral neighbors on their own tab, with what a glance shows", async () => {
        getSample.mockResolvedValue(SAMPLE_DETAIL);
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([
            {
                hash: "d".repeat(64),
                distance: 1.5,
                playback_rate_hz: null,
                display_name: "snare_909",
                category: "snare",
                hand_label: null,
                thumbnail: null,
            },
        ]);
        useSelectionStore.getState().focusSample("abc");
        renderPanel();

        fireEvent.click(await screen.findByRole("button", { name: "Similar (1)" }));

        expect(screen.getByText("dddddddd")).toBeInTheDocument();
        expect(screen.getByText("snare_909")).toBeInTheDocument();
        expect(screen.getByText("1.500")).toBeInTheDocument();
        expect(screen.queryByRole("link", { name: "A Song" })).not.toBeInTheDocument();
    });

    it("shows an honest empty state when the sample has no spectral neighbors yet", async () => {
        getSample.mockResolvedValue(SAMPLE_DETAIL);
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockRejectedValue(new ApiError(404, "not found"));
        useSelectionStore.getState().focusSample("abc");
        renderPanel();

        fireEvent.click(await screen.findByRole("button", { name: "Similar (0)" }));

        expect(screen.getByText(/No spectral neighbors yet/)).toBeInTheDocument();
    });

    it("keeps the chosen tab when the focus moves to another sample", async () => {
        getSample.mockImplementation((hash: string) =>
            Promise.resolve({ ...SAMPLE_DETAIL, hash, display_name: hash === "abc" ? "kick" : "snare" }),
        );
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");
        renderPanel();
        fireEvent.click(await screen.findByRole("button", { name: "Similar (0)" }));

        act(() => {
            useSelectionStore.getState().focusSample("xyz");
        });

        await screen.findByRole("heading", { name: "snare" });
        expect(screen.getByRole("button", { name: "Similar (0)" })).toHaveAttribute("aria-pressed", "true");
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
