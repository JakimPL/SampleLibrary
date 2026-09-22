import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type * as SamplesApi from "../../src/api/samples";
import { FocusedSampleTransport } from "../../src/samples/SampleTransport";

const { instances, createMock, getSample, getSampleRelations, getSimilarSamples } = vi.hoisted(() => {
    class FakeWaveSurfer {
        private readonly listeners = new Map<string, ((...args: unknown[]) => void)[]>();
        readonly play = vi.fn().mockResolvedValue(undefined);
        readonly pause = vi.fn();
        readonly setTime = vi.fn();
        readonly setPlaybackRate = vi.fn();
        readonly setOptions = vi.fn();
        readonly destroy = vi.fn();

        on(event: string, callback: (...args: unknown[]) => void): () => void {
            const callbacks = this.listeners.get(event) ?? [];
            callbacks.push(callback);
            this.listeners.set(event, callbacks);
            return () => undefined;
        }

        emit(event: string, ...args: unknown[]): void {
            for (const callback of this.listeners.get(event) ?? []) {
                callback(...args);
            }
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

vi.mock("../../src/api/samples", async () => {
    const actual = await vi.importActual<typeof SamplesApi>("../../src/api/samples");
    return { ...actual, getSample, getSampleRelations, getSimilarSamples };
});

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

function catalogAnswers(overrides: SampleDetailOverrides): void {
    getSample.mockResolvedValue({
        hash: "abc",
        depth: 16,
        channels: 1,
        frames: 4096,
        display_name: "kick",
        size_bytes: 8192,
        duration_seconds: 0.09,
        playback_rate_hz: overrides.playbackRateHz,
        playback_rates: overrides.playbackRates ?? [],
        categories: [],
        occurrences: [],
        files: [],
    });
    getSampleRelations.mockResolvedValue([]);
    getSimilarSamples.mockResolvedValue([]);
}

const TWO_RATES: readonly PlaybackRateFixture[] = [
    { rate_hz: 22050, event_count: 40 },
    { rate_hz: 8363, event_count: 2 },
];

describe("FocusedSampleTransport", () => {
    it("plays the sample at the rate the library really sounds it at", async () => {
        catalogAnswers({ playbackRateHz: 22050, playbackRates: TWO_RATES });

        render(<FocusedSampleTransport sampleHash="abc" />);

        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });
        await waitFor(() => {
            expect(createMock).toHaveBeenCalled();
        });
        act(() => {
            latestInstance().emit("ready", 1.0);
        });
        await waitFor(() => {
            expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(22050 / 44100, false);
        });
    });

    it("lets the person hear another rate the library plays the sample at", async () => {
        catalogAnswers({ playbackRateHz: 22050, playbackRates: TWO_RATES });
        render(<FocusedSampleTransport sampleHash="abc" />);
        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: "8363" } });

        await waitFor(() => {
            expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(8363 / 44100, false);
        });
    });

    it("says so for a sample the catalog knows no rate for", async () => {
        catalogAnswers({ playbackRateHz: null });

        render(<FocusedSampleTransport sampleHash="abc" />);

        expect(await screen.findByText(/no rate the library is known to play it at/)).toBeInTheDocument();
        expect(createMock).not.toHaveBeenCalled();
    });

    it("says what went wrong when the catalog has no such sample", async () => {
        getSample.mockRejectedValue(new Error("no sample cataloged with hash 'abc'"));
        getSampleRelations.mockResolvedValue([]);
        getSimilarSamples.mockResolvedValue([]);

        render(<FocusedSampleTransport sampleHash="abc" />);

        expect(await screen.findByRole("alert")).toHaveTextContent("no sample cataloged with hash 'abc'");
    });
});
