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

/** The waveform the panel built. Created by an effect of its own, so callers wait for it. */
function latestInstance(): (typeof instances)[number] {
    const instance = instances[instances.length - 1];
    if (instance === undefined) {
        throw new Error("no FakeWaveSurfer instance was created");
    }
    return instance;
}

interface PlaybackRateFixture {
    readonly rate_hz: number;
    readonly event_count: number;
}

interface SampleDetailOverrides {
    readonly playbackRateHz: number | null;
    readonly playbackRates?: readonly PlaybackRateFixture[];
}

function buildSampleDetail(overrides: SampleDetailOverrides): unknown {
    return {
        hash: "abc",
        depth: 16,
        channels: 1,
        frames: 4096,
        display_name: "kick",
        category: "kick",
        size_bytes: 8192,
        duration_seconds: 0.09,
        playback_rate_hz: overrides.playbackRateHz,
        playback_rates: overrides.playbackRates ?? [],
        occurrences: [],
    };
}

describe("WaveformPanel", () => {
    it("shows a placeholder when no sample is focused", () => {
        render(<WaveformPanel />);

        expect(screen.getByText(/No sample focused yet/)).toBeInTheDocument();
    });

    it("plays the focused sample at the rate the library really sounds it at", async () => {
        getSample.mockResolvedValue(
            buildSampleDetail({
                playbackRateHz: 22050,
                playbackRates: [
                    { rate_hz: 22050, event_count: 40 },
                    { rate_hz: 8363, event_count: 2 },
                ],
            }),
        );
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");

        render(<WaveformPanel />);

        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });
        await waitFor(() => {
            expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(22050 / 44100, false);
        });
    });

    it("lets the user hear another rate the library plays the sample at", async () => {
        getSample.mockResolvedValue(
            buildSampleDetail({
                playbackRateHz: 22050,
                playbackRates: [
                    { rate_hz: 22050, event_count: 40 },
                    { rate_hz: 8363, event_count: 2 },
                ],
            }),
        );
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");
        render(<WaveformPanel />);
        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: "8363" } });

        await waitFor(() => {
            expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(8363 / 44100, false);
        });
    });

    it("shows an honest empty state for a sample the catalog knows no rate for", async () => {
        getSample.mockResolvedValue(buildSampleDetail({ playbackRateHz: null }));
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);
        useSelectionStore.getState().focusSample("abc");

        render(<WaveformPanel />);

        await waitFor(() => {
            expect(screen.getByText(/no rate the library is known to play it at/)).toBeInTheDocument();
        });
    });

    it("shares one request with SampleDetailPanel for the same focused sample", async () => {
        getSample.mockResolvedValue(
            buildSampleDetail({
                playbackRateHz: 8363,
                playbackRates: [
                    { rate_hz: 8363, event_count: 2 },
                    { rate_hz: 16726, event_count: 1 },
                ],
            }),
        );
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
