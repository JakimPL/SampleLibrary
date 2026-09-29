import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { SampleDetail } from "../../src/api/samples";
import { SampleTransport } from "../../src/samples/SampleTransport";

const { instances, createMock } = vi.hoisted(() => {
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
    return { instances, createMock };
});

vi.mock("wavesurfer.js", () => ({
    default: { create: createMock },
}));

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

function sampleOf(overrides: SampleDetailOverrides): SampleDetail {
    return {
        hash: "abc",
        depth: 16,
        channels: 1,
        frames: 4096,
        display_name: "kick",
        category: null,
        hand_label: null,
        rating: null,
        favorite: false,
        equivalence_member_count: 1,
        size_bytes: 8192,
        duration_seconds: 0.09,
        playback_rate_hz: overrides.playbackRateHz,
        playback_rates: overrides.playbackRates ?? [],
        categories: [],
        occurrences: [],
        files: [],
    };
}

const TWO_RATES: readonly PlaybackRateFixture[] = [
    { rate_hz: 22050, event_count: 40 },
    { rate_hz: 8363, event_count: 2 },
];

describe("SampleTransport", () => {
    it("plays the sample at the rate the library really sounds it at", async () => {
        render(<SampleTransport sample={sampleOf({ playbackRateHz: 22050, playbackRates: TWO_RATES })} />);

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
        render(<SampleTransport sample={sampleOf({ playbackRateHz: 22050, playbackRates: TWO_RATES })} />);
        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });
        await waitFor(() => {
            expect(createMock).toHaveBeenCalled();
        });

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: "8363" } });

        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(8363 / 44100, false);
    });

    it("plays a rate chosen while the waveform loads once it is ready", async () => {
        render(<SampleTransport sample={sampleOf({ playbackRateHz: 22050, playbackRates: TWO_RATES })} />);
        await waitFor(() => {
            expect(screen.getByLabelText("Rate")).toHaveValue("22050");
        });
        await waitFor(() => {
            expect(createMock).toHaveBeenCalled();
        });

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: "8363" } });
        act(() => {
            latestInstance().emit("ready", 1.0);
        });

        expect(latestInstance().setPlaybackRate).toHaveBeenLastCalledWith(8363 / 44100, false);
    });

    it("says so for a sample the catalog knows no rate for", () => {
        render(<SampleTransport sample={sampleOf({ playbackRateHz: null })} />);

        expect(screen.getByText(/no rate the library is known to play it at/)).toBeInTheDocument();
        expect(createMock).not.toHaveBeenCalled();
    });
});
