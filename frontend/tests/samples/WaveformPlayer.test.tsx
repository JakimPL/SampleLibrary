import { act, fireEvent, render, renderHook, type RenderResult, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { PHONE_MEDIA_QUERY } from "../../src/layout/layoutMode";
import { NOMINAL_WAV_RATE_HZ } from "../../src/samples/nominalRate";
import { samplePreview, useAudioPreview } from "../../src/samples/useAudioPreview";
import type { RateOption } from "../../src/samples/WaveformPlayer";
import { WaveformPlayer } from "../../src/samples/WaveformPlayer";
import { stubMatchMedia } from "../support/matchMedia";

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
    readonly fileName?: string;
    readonly rateHz?: number;
    readonly rateOptions?: readonly RateOption[];
    readonly onRateChange?: (rateHz: number) => void;
}

function renderPlayer(overrides: PlayerOverrides = {}): RenderResult {
    return render(
        <WaveformPlayer
            sampleHash="abc"
            fileName={overrides.fileName ?? "crash cymbal.wav"}
            rateHz={overrides.rateHz ?? 8363}
            rateOptions={overrides.rateOptions ?? [{ rateHz: 8363, eventCount: 1 }]}
            onRateChange={overrides.onRateChange ?? vi.fn()}
        />,
    );
}

describe("WaveformPlayer", () => {
    it("says the audio is unavailable when wavesurfer cannot load it", () => {
        renderPlayer();

        act(() => {
            latestInstance().emit("error", new Error("404"));
        });

        expect(screen.getByText(/Audio unavailable/)).toBeInTheDocument();
        expect(screen.getByRole("button")).toBeDisabled();
    });

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

    it("offers the sample as a file, named as the library calls it", () => {
        renderPlayer({ fileName: "crash cymbal.wav" });

        const save = screen.getByRole("link", { name: "Save this sample" });
        expect(save).toHaveAttribute("href", "/api/samples/abc/audio");
        expect(save).toHaveAttribute("download", "crash cymbal.wav");
    });

    it("keeps to one voice with the shared preview element", () => {
        renderPlayer();
        const preview = renderHook(() => useAudioPreview());
        act(() => {
            latestInstance().emit("ready", 1.0);
        });
        act(() => {
            preview.result.current.play(samplePreview("other", null));
        });

        fireEvent.click(screen.getByRole("button"));
        expect(preview.result.current.playingKey).toBeNull();
        expect(latestInstance().play).toHaveBeenCalled();

        act(() => {
            latestInstance().emit("play");
        });
        act(() => {
            preview.result.current.play(samplePreview("another", null));
        });

        expect(latestInstance().pause).toHaveBeenCalled();
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

describe("WaveformPlayer on a phone", () => {
    beforeEach(() => {
        stubMatchMedia(new Set([PHONE_MEDIA_QUERY]));
    });

    it("plays from one row, at the rate the library plays it, the file to save at the row's end and no rate to choose", () => {
        const { container } = renderPlayer({
            rateOptions: [
                { rateHz: 8363, eventCount: 1 },
                { rateHz: NOMINAL_WAV_RATE_HZ, eventCount: 2 },
            ],
        });

        expect(container.querySelector(".wave-panel")).toHaveClass("wave-panel-compact");
        expect(screen.queryByLabelText("Rate")).not.toBeInTheDocument();
        expect(container.querySelector(".wave-panel > :last-child")).toBe(
            screen.getByRole("link", { name: "Save this sample" }),
        );
        act(() => {
            latestInstance().emit("ready", 1.0);
        });
        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(8363 / NOMINAL_WAV_RATE_HZ, false);
    });

    it("reads the time in the frame's corner", () => {
        const { container } = renderPlayer();

        act(() => {
            latestInstance().emit("ready", 0.93);
        });
        expect(container.querySelector(".wave-panel-frame .wave-time")).toHaveTextContent("0.00 s / 0.93 s");

        act(() => {
            latestInstance().emit("timeupdate", 0.5);
        });
        expect(container.querySelector(".wave-time")).toHaveTextContent("0.50 s / 0.93 s");
    });

    it("plays and pauses from its one button", () => {
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
    });

    it("says in the frame itself when the audio cannot be loaded", () => {
        const { container } = renderPlayer();

        act(() => {
            latestInstance().emit("error", new Error("404"));
        });

        expect(screen.getByRole("status")).toHaveTextContent(/Audio unavailable/);
        expect(container.querySelector(".wave-time")).not.toBeInTheDocument();
        expect(screen.getByRole("button")).toBeDisabled();
    });
});
