import { act, render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { describe, expect, it, vi } from "vitest";

import { NOMINAL_WAV_RATE_HZ } from "../../src/samples/nominalRate";
import { useWaveformPlayer, type WaveformPlayer } from "../../src/samples/useWaveformPlayer";
import { useThemeStore } from "../../src/theme/themeStore";

const { instances, createMock } = vi.hoisted(() => {
    class FakeWaveSurfer {
        readonly options: unknown;
        private readonly listeners = new Map<string, ((...args: unknown[]) => void)[]>();
        readonly play = vi.fn().mockResolvedValue(undefined);
        readonly pause = vi.fn();
        readonly setTime = vi.fn();
        readonly setPlaybackRate = vi.fn();
        readonly setOptions = vi.fn();
        readonly destroy = vi.fn();

        constructor(options: unknown) {
            this.options = options;
        }

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
    const createMock = vi.fn((options: unknown) => {
        const instance = new FakeWaveSurfer(options);
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

function Harness({ audioUrl, rateHz }: { audioUrl: string; rateHz: number }): ReactElement {
    const player: WaveformPlayer = useWaveformPlayer(audioUrl, rateHz);
    return (
        <div>
            <div data-testid="container" ref={player.containerRef} />
            <span data-testid="state">
                {player.isReady ? "ready" : "not-ready"}/{player.isPlaying ? "playing" : "paused"}
            </span>
        </div>
    );
}

describe("useWaveformPlayer", () => {
    it("creates a wavesurfer instance against its own container once mounted", () => {
        render(<Harness audioUrl="/samples/abc/audio" rateHz={8363} />);

        expect(createMock).toHaveBeenCalledTimes(1);
        const options = createMock.mock.calls[0]?.[0] as { url: string; container: HTMLElement };
        expect(options.url).toBe("/samples/abc/audio");
        expect(options.container).toBe(screen.getByTestId("container"));
    });

    it("applies the initial rate without preserving pitch", () => {
        render(<Harness audioUrl="/samples/abc/audio" rateHz={NOMINAL_WAV_RATE_HZ * 2} />);

        expect(latestInstance().setPlaybackRate).toHaveBeenCalledWith(2, false);
    });

    it("reflects ready and playing state as wavesurfer emits its own events", () => {
        render(<Harness audioUrl="/samples/abc/audio" rateHz={8363} />);
        expect(screen.getByTestId("state")).toHaveTextContent("not-ready/paused");

        act(() => {
            latestInstance().emit("ready", 1.5);
            latestInstance().emit("play");
        });
        expect(screen.getByTestId("state")).toHaveTextContent("ready/playing");

        act(() => {
            latestInstance().emit("pause");
        });
        expect(screen.getByTestId("state")).toHaveTextContent("ready/paused");
    });

    it("destroys the instance when the component unmounts", () => {
        const { unmount } = render(<Harness audioUrl="/samples/abc/audio" rateHz={8363} />);
        const instance = latestInstance();

        unmount();

        expect(instance.destroy).toHaveBeenCalled();
    });

    it("creates a new instance when the audio URL changes", () => {
        const { rerender } = render(<Harness audioUrl="/samples/abc/audio" rateHz={8363} />);
        const firstInstance = latestInstance();

        rerender(<Harness audioUrl="/samples/def/audio" rateHz={8363} />);

        expect(firstInstance.destroy).toHaveBeenCalled();
        expect(createMock).toHaveBeenCalledTimes(2);
    });

    it("creates the instance with theme-driven wave, progress, and cursor colors", () => {
        render(<Harness audioUrl="/samples/abc/audio" rateHz={8363} />);

        const options = createMock.mock.calls[0]?.[0] as {
            waveColor?: string;
            progressColor?: string;
            cursorColor?: string;
        };
        expect(options.waveColor).toBeTruthy();
        expect(options.progressColor).toBeTruthy();
        expect(options.cursorColor).toBeTruthy();
    });

    it("re-applies colors through setOptions when the theme preference changes", () => {
        render(<Harness audioUrl="/samples/abc/audio" rateHz={8363} />);
        const instance = latestInstance();
        instance.setOptions.mockClear();

        act(() => {
            useThemeStore.getState().setPreference("openmpt");
        });

        expect(instance.setOptions).toHaveBeenCalled();
    });
});
