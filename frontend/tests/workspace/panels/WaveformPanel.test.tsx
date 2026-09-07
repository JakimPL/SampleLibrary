import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../../src/api/samples";
import { SampleDetailPanel } from "../../../src/workspace/panels/SampleDetailPanel";
import { WaveformPanel } from "../../../src/workspace/panels/WaveformPanel";
import { useSelectionStore } from "../../../src/workspace/selectionStore";

const { instances, createMock, getSample, getSampleRelations, getSimilarSamples } = vi.hoisted(() => {
    class FakeWaveSurfer {
        readonly play = vi.fn().mockResolvedValue(undefined);
        readonly pause = vi.fn();
        readonly setTime = vi.fn();
        readonly setPlaybackRate = vi.fn();
        readonly setOptions = vi.fn();
        readonly destroy = vi.fn();
        on(): () => void {
            return () => undefined;
        }
    }
    const instances: FakeWaveSurfer[] = [];
    const createMock = vi.fn(() => {
        const instance = new FakeWaveSurfer();
        instances.push(instance);
        return instance;
    });
    return { instances, createMock, getSample: vi.fn(), getSampleRelations: vi.fn(), getSimilarSamples: vi.fn() };
});

vi.mock("wavesurfer.js", () => ({
    default: { create: createMock },
}));

vi.mock("../../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples };
});

function latestInstance(): (typeof instances)[number] {
    const instance = instances[instances.length - 1];
    if (instance === undefined) {
        throw new Error("no FakeWaveSurfer instance was created");
    }
    return instance;
}

function buildSampleDetail(overrides: { readonly dominantRateHz: number | null; readonly rates: number[] }): unknown {
    return {
        hash: "abc",
        depth: 16,
        channels: 1,
        frames: 4096,
        display_name: "kick",
        category: "kick",
        size_bytes: 8192,
        duration_seconds: 0.09,
        dominant_rate_hz: overrides.dominantRateHz,
        occurrences: overrides.rates.map((rate, index) => ({
            properties: {
                sample_hash: "abc",
                occurrence: { module_hash: "module-1", instrument_index: 0, sample_slot: index },
                name: "kick",
                rate,
                volume: 64,
                tracker: "xm",
                tuning: { relative_note: 0, finetune: 0 },
            },
            module: { hash: "module-1", title: "A Song", filename: "song.xm", tracker: "xm" },
        })),
    };
}

describe("WaveformPanel", () => {
    it("shows a placeholder when no sample is focused", () => {
        render(<WaveformPanel />);

        expect(screen.getByText(/No sample focused yet/)).toBeInTheDocument();
    });

    it("plays the focused sample at its dominant rate by default", async () => {
        getSample.mockResolvedValue(buildSampleDetail({ dominantRateHz: 22050, rates: [8363, 22050, 22050] }));
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");

        render(<WaveformPanel />);

        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });
        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(22050 / 44100, false);
    });

    it("lets the user switch to a different occurrence's rate", async () => {
        getSample.mockResolvedValue(buildSampleDetail({ dominantRateHz: 22050, rates: [8363, 22050] }));
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");
        render(<WaveformPanel />);
        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: "8363" } });

        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(8363 / 44100, false);
    });

    it("shows an honest empty state for a sample with no occurrences", async () => {
        getSample.mockResolvedValue(buildSampleDetail({ dominantRateHz: null, rates: [] }));
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");

        render(<WaveformPanel />);

        await waitFor(() => {
            expect(screen.getByText(/no occurrences to play at a real tracker rate/)).toBeInTheDocument();
        });
    });

    it("shares one request with SampleDetailPanel for the same focused sample", async () => {
        getSample.mockResolvedValue(buildSampleDetail({ dominantRateHz: 8363, rates: [8363] }));
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");

        render(
            <MemoryRouter>
                <SampleDetailPanel />
                <WaveformPanel />
            </MemoryRouter>,
        );

        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toBeInTheDocument();
        });
        expect(getSample).toHaveBeenCalledTimes(1);
    });
});
