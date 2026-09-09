import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NOMINAL_WAV_RATE_HZ } from "../../src/samples/nominalRate";
import { previewPlaybackRate, useAudioPreview } from "../../src/samples/useAudioPreview";

describe("previewPlaybackRate", () => {
    it("plays the stored file as it stands when no rate is known", () => {
        expect(previewPlaybackRate(null)).toBe(1);
    });

    it("runs the stored file at the ratio between the library's rate and the file's own", () => {
        expect(previewPlaybackRate(8363)).toBeCloseTo(8363 / NOMINAL_WAV_RATE_HZ);
    });

    it("sounds a sample the library reads twice as fast at twice the speed", () => {
        expect(previewPlaybackRate(16726)).toBeCloseTo((8363 * 2) / NOMINAL_WAV_RATE_HZ);
    });
});

describe("useAudioPreview", () => {
    it("tracks the most recently played sample as playing", () => {
        const { result } = renderHook(() => useAudioPreview());

        act(() => {
            result.current.play("sample-preview-a", null);
        });

        expect(result.current.playingHash).toBe("sample-preview-a");
    });

    it("playing a different sample replaces which one is tracked as playing", () => {
        const { result } = renderHook(() => useAudioPreview());

        act(() => {
            result.current.play("sample-preview-b", null);
        });
        act(() => {
            result.current.play("sample-preview-c", null);
        });

        expect(result.current.playingHash).toBe("sample-preview-c");
    });

    it("two hook instances observe the same playing sample", () => {
        const first = renderHook(() => useAudioPreview());
        const second = renderHook(() => useAudioPreview());

        act(() => {
            first.result.current.play("sample-preview-d", null);
        });

        expect(second.result.current.playingHash).toBe("sample-preview-d");
    });
});

describe("the shared preview element", () => {
    it("names the rate after the source, so loading the file cannot take the rate back", async () => {
        const writes: string[] = [];

        class RecordingAudio {
            defaultPlaybackRate = 1;
            preservesPitch = true;
            private storedSource = "";
            private storedPlaybackRate = 1;

            get src(): string {
                return this.storedSource;
            }

            set src(source: string) {
                writes.push("src");
                this.storedSource = source;
                // What a real media element does with a new source, and the whole point of the
                // order under test: the rate goes back to the default before the file plays.
                this.storedPlaybackRate = this.defaultPlaybackRate;
            }

            get playbackRate(): number {
                return this.storedPlaybackRate;
            }

            set playbackRate(rate: number) {
                writes.push("playbackRate");
                this.storedPlaybackRate = rate;
            }

            addEventListener(): void {
                // no media pipeline to report an ending
            }

            play(): Promise<void> {
                return Promise.resolve();
            }

            pause(): void {
                // no media pipeline to pause
            }
        }

        const element = new RecordingAudio();
        // Every `new Audio()` in the module under test hands back this one recording element.
        function audioConstructorStub(): RecordingAudio {
            return element;
        }

        vi.stubGlobal("Audio", audioConstructorStub);
        vi.resetModules();
        const { useAudioPreview: freshUseAudioPreview } = await import("../../src/samples/useAudioPreview");
        const { result } = renderHook(() => freshUseAudioPreview());

        act(() => {
            result.current.play("sample-preview-e", 8363);
        });

        expect(writes).toEqual(["src", "playbackRate"]);
        expect(element.playbackRate).toBeCloseTo(8363 / NOMINAL_WAV_RATE_HZ);
        vi.unstubAllGlobals();
    });
});
