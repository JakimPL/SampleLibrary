import { act, fireEvent, render, type RenderResult, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NOMINAL_WAV_RATE_HZ } from "../../src/samples/nominalRate";
import type { RateOption } from "../../src/samples/WaveformPlayer";
import { WaveformPlayer } from "../../src/samples/WaveformPlayer";

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

interface PlayerOverrides {
    readonly rateHz?: number;
    readonly rateOptions?: readonly RateOption[];
    readonly onRateChange?: (rateHz: number) => void;
}

function renderPlayer(overrides: PlayerOverrides = {}): RenderResult {
    return render(
        <WaveformPlayer
            sampleHash="abc"
            rateHz={overrides.rateHz ?? 8363}
            rateOptions={overrides.rateOptions ?? [{ rateHz: 8363, eventCount: 1 }]}
            onRateChange={overrides.onRateChange ?? vi.fn()}
        />,
    );
}

describe("WaveformPlayer", () => {
    it("disables the play button until wavesurfer reports ready", () => {
        renderPlayer();

        expect(screen.getByRole("button")).toBeDisabled();

        act(() => {
            latestInstance().emit("ready", 1.0);
        });

        expect(screen.getByRole("button")).toBeEnabled();
    });

    it("plays and shows the pause glyph once playing, toggling back on a second click", () => {
        renderPlayer();
        act(() => {
            latestInstance().emit("ready", 1.0);
        });

        fireEvent.click(screen.getByRole("button"));
        expect(latestInstance().play).toHaveBeenCalled();

        act(() => {
            latestInstance().emit("play");
        });
        expect(screen.getByRole("button")).toHaveTextContent("⏸");

        fireEvent.click(screen.getByRole("button"));
        expect(latestInstance().pause).toHaveBeenCalled();
    });

    it("annotates each rate option with how often the library plays it there", () => {
        renderPlayer({
            rateOptions: [
                { rateHz: 8363, eventCount: 1 },
                { rateHz: NOMINAL_WAV_RATE_HZ, eventCount: 2 },
            ],
        });

        expect(screen.getByRole("option", { name: "8363 Hz · played 1 time" })).toBeInTheDocument();
        expect(
            screen.getByRole("option", { name: `${String(NOMINAL_WAV_RATE_HZ)} Hz · played 2 times` }),
        ).toBeInTheDocument();
    });

    it("offers no choice for a sample the library plays at one rate throughout", () => {
        renderPlayer();

        expect(screen.queryByLabelText("Rate")).not.toBeInTheDocument();
    });

    it("applies a newly selected rate and reports it to the caller", () => {
        const onRateChange = vi.fn();
        renderPlayer({
            rateOptions: [
                { rateHz: 8363, eventCount: 1 },
                { rateHz: NOMINAL_WAV_RATE_HZ, eventCount: 2 },
            ],
            onRateChange,
        });

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: String(NOMINAL_WAV_RATE_HZ) } });

        expect(onRateChange).toHaveBeenCalledWith(NOMINAL_WAV_RATE_HZ);
        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(1, false);
    });

    it("opens at the rate it was handed, against the stored file's own", () => {
        renderPlayer({ rateHz: 16726 });

        act(() => {
            latestInstance().emit("ready", 1.0);
        });

        expect(createMock).toHaveBeenLastCalledWith(expect.objectContaining({ url: "/api/samples/abc/audio" }));
        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(16726 / NOMINAL_WAV_RATE_HZ, false);
    });

    it("marks the waveform as sounding only while it is playing", () => {
        const { container } = renderPlayer();
        const canvas = container.querySelector(".wave-canvas-wrap");

        act(() => {
            latestInstance().emit("ready", 1.0);
        });
        expect(canvas).not.toHaveClass("is-playing");

        act(() => {
            latestInstance().emit("play");
        });
        expect(canvas).toHaveClass("is-playing");

        act(() => {
            latestInstance().emit("finish");
        });
        expect(canvas).not.toHaveClass("is-playing");
    });
});
