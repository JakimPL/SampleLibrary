import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NOMINAL_WAV_RATE_HZ } from "../../src/samples/nominalRate";
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

describe("WaveformPlayer", () => {
    it("disables the play button until wavesurfer reports ready", () => {
        render(
            <WaveformPlayer
                sampleHash="abc"
                rateHz={8363}
                rateOptions={[{ rateHz: 8363, occurrenceCount: 1 }]}
                onRateChange={vi.fn()}
            />,
        );

        expect(screen.getByRole("button")).toBeDisabled();

        act(() => {
            latestInstance().emit("ready", 1.0);
        });

        expect(screen.getByRole("button")).toBeEnabled();
    });

    it("plays and shows the pause glyph once playing, toggling back on a second click", () => {
        render(
            <WaveformPlayer
                sampleHash="abc"
                rateHz={8363}
                rateOptions={[{ rateHz: 8363, occurrenceCount: 1 }]}
                onRateChange={vi.fn()}
            />,
        );
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

    it("annotates each rate option with how many occurrences use it", () => {
        render(
            <WaveformPlayer
                sampleHash="abc"
                rateHz={8363}
                rateOptions={[
                    { rateHz: 8363, occurrenceCount: 1 },
                    { rateHz: NOMINAL_WAV_RATE_HZ, occurrenceCount: 2 },
                ]}
                onRateChange={vi.fn()}
            />,
        );

        expect(screen.getByRole("option", { name: "8363 Hz · used in 1 occurrence" })).toBeInTheDocument();
        expect(
            screen.getByRole("option", { name: `${String(NOMINAL_WAV_RATE_HZ)} Hz · used in 2 occurrences` }),
        ).toBeInTheDocument();
    });

    it("explains why pitch tracks the selected rate", () => {
        render(
            <WaveformPlayer
                sampleHash="abc"
                rateHz={8363}
                rateOptions={[{ rateHz: 8363, occurrenceCount: 1 }]}
                onRateChange={vi.fn()}
            />,
        );

        expect(screen.getByText(/no fixed rate of its own/)).toBeInTheDocument();
    });

    it("applies a newly selected rate and reports it to the caller", () => {
        const onRateChange = vi.fn();
        render(
            <WaveformPlayer
                sampleHash="abc"
                rateHz={8363}
                rateOptions={[
                    { rateHz: 8363, occurrenceCount: 1 },
                    { rateHz: NOMINAL_WAV_RATE_HZ, occurrenceCount: 2 },
                ]}
                onRateChange={onRateChange}
            />,
        );

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: String(NOMINAL_WAV_RATE_HZ) } });

        expect(onRateChange).toHaveBeenCalledWith(NOMINAL_WAV_RATE_HZ);
        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(1, false);
    });
});
