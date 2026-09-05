import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../src/api/samples";
import { SampleDetailPage } from "../../src/samples/SampleDetailPage";

const { getSample, getSampleRelations, getSampleWaveform } = vi.hoisted(() => ({
    getSample: vi.fn(),
    getSampleRelations: vi.fn(),
    getSampleWaveform: vi.fn(),
}));

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSampleWaveform };
});

function renderPage(): ReturnType<typeof render> {
    return render(
        <MemoryRouter initialEntries={["/samples/sample-1"]}>
            <Routes>
                <Route path="/samples/:sampleHash" element={<SampleDetailPage />} />
            </Routes>
        </MemoryRouter>,
    );
}

function occurrence(overrides: { readonly name?: string; readonly moduleTitle?: string } = {}): unknown {
    return {
        properties: {
            sample_hash: "sample-1",
            occurrence: { module_hash: "module-1", instrument_index: 0, sample_slot: 0 },
            name: overrides.name ?? "lead",
            rate: 8363,
            volume: 64,
            tracker: "xm",
            tuning: { relative_note: 0, finetune: 0 },
        },
        module: {
            hash: "module-1",
            filename: "song.xm",
            title: overrides.moduleTitle ?? "a song",
            tracker: "xm",
        },
    };
}

describe("SampleDetailPage", () => {
    it("renders the resolved name, module context, and occurrence count", async () => {
        getSample.mockResolvedValue({
            hash: "sample-1",
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [occurrence()],
            size_bytes: 8192,
            display_name: "kick",
            duration_seconds: 0.5,
        });
        getSampleRelations.mockResolvedValue([]);
        getSampleWaveform.mockResolvedValue([{ minimum: -0.5, maximum: 0.5 }]);

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("heading", { name: "kick" })).toBeInTheDocument();
        });
        const moduleLink = screen.getByRole("link", { name: "a song" });
        expect(moduleLink).toHaveAttribute("href", "/modules/module-1");
        expect(moduleLink.closest("td")).toHaveTextContent("song.xm");
        const occurrencesTerm = screen.getAllByText("Occurrences").find((element) => element.tagName === "DT");
        expect(occurrencesTerm?.nextElementSibling).toHaveTextContent("1");
    });

    it("falls back to the [unnamed] placeholder for an unresolved display name", async () => {
        getSample.mockResolvedValue({
            hash: "sample-1",
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [occurrence({ name: "" })],
            size_bytes: 0,
            display_name: "",
            duration_seconds: 0,
        });
        getSampleRelations.mockResolvedValue([]);
        getSampleWaveform.mockResolvedValue([]);

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("heading", { name: "[unnamed]" })).toBeInTheDocument();
        });
    });

    it("renders the waveform canvas and an audio player pointed at the sample's own audio", async () => {
        getSample.mockResolvedValue({
            hash: "sample-1",
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [],
            size_bytes: 0,
            display_name: "kick",
            duration_seconds: 0.1,
        });
        getSampleRelations.mockResolvedValue([]);
        getSampleWaveform.mockResolvedValue([{ minimum: -1, maximum: 1 }]);

        renderPage();

        await waitFor(() => {
            expect(document.querySelector("canvas")).toBeInTheDocument();
        });
        expect(document.querySelector("audio")).toHaveAttribute("src", "/samples/sample-1/audio");
    });

    it("shows an explicit empty state when a sample has no relations", async () => {
        getSample.mockResolvedValue({
            hash: "sample-1",
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [],
            size_bytes: 0,
            display_name: "kick",
            duration_seconds: 0.1,
        });
        getSampleRelations.mockResolvedValue([]);
        getSampleWaveform.mockResolvedValue([]);

        renderPage();

        await waitFor(() => {
            expect(screen.getByText("No relations found for this sample.")).toBeInTheDocument();
        });
    });

    it("links a relation to the other sample in the pair", async () => {
        getSample.mockResolvedValue({
            hash: "sample-1",
            depth: 16,
            channels: 1,
            frames: 4096,
            occurrences: [],
            size_bytes: 0,
            display_name: "kick",
            duration_seconds: 0.1,
        });
        getSampleRelations.mockResolvedValue([
            {
                id: 1,
                subject_hash: "sample-1",
                reference_hash: "sample-2",
                relation_type: "bit_depth_variant",
                method: "bit_depth_variant/mse_v1",
                confidence: 0.9,
                evidence: {},
                detected_at: "2026-01-01T00:00:00Z",
            },
        ]);
        getSampleWaveform.mockResolvedValue([]);

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("link", { name: "sample-2" })).toHaveAttribute("href", "/samples/sample-2");
        });
        expect(screen.getByText("bit_depth_variant/mse_v1")).toBeInTheDocument();
        expect(screen.getByText("Unreviewed")).toBeInTheDocument();
    });

    it("shows an error notice when the sample cannot be found", async () => {
        getSample.mockRejectedValue(new Error("no sample catalogued with hash 'sample-1'"));
        getSampleRelations.mockRejectedValue(new Error("no sample catalogued with hash 'sample-1'"));
        getSampleWaveform.mockRejectedValue(new Error("no sample catalogued with hash 'sample-1'"));

        renderPage();

        await waitFor(() => {
            expect(screen.getByRole("alert")).toHaveTextContent("no sample catalogued with hash 'sample-1'");
        });
    });
});
