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
        render(<WaveformPlayer sampleHash="abc" rateHz={8363} rateOptions={[8363]} onRateChange={vi.fn()} />);

        expect(screen.getByRole("button")).toBeDisabled();

        act(() => {
            latestInstance().emit("ready", 1.0);
        });

        expect(screen.getByRole("button")).toBeEnabled();
    });

    it("plays and shows the pause glyph once playing, toggling back on a second click", () => {
        render(<WaveformPlayer sampleHash="abc" rateHz={8363} rateOptions={[8363]} onRateChange={vi.fn()} />);
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

    it("applies a newly selected rate and reports it to the caller", () => {
        const onRateChange = vi.fn();
        render(
            <WaveformPlayer
                sampleHash="abc"
                rateHz={8363}
                rateOptions={[8363, NOMINAL_WAV_RATE_HZ]}
                onRateChange={onRateChange}
            />,
        );

        fireEvent.change(screen.getByLabelText("Rate"), { target: { value: String(NOMINAL_WAV_RATE_HZ) } });

        expect(onRateChange).toHaveBeenCalledWith(NOMINAL_WAV_RATE_HZ);
        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(1, false);
    });
});
