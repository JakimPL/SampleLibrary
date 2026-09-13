import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NOMINAL_WAV_RATE_HZ } from "../../src/samples/nominalRate";
import { previewPlaybackRate, samplePreview, useAudioPreview } from "../../src/samples/useAudioPreview";

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

describe("samplePreview", () => {
    it("keys a sample's preview by its hash and points it at the sample's audio route", () => {
        const source = samplePreview("a".repeat(64), 8363);

        expect(source.key).toBe("a".repeat(64));
        expect(source.url).toBe(`/api/samples/${"a".repeat(64)}/audio`);
        expect(source.playbackRateHz).toBe(8363);
    });
});

describe("useAudioPreview", () => {
    it("tracks the most recently played source as playing", () => {
        const { result } = renderHook(() => useAudioPreview());

        act(() => {
            result.current.play(samplePreview("sample-preview-a", null));
        });

        expect(result.current.playingKey).toBe("sample-preview-a");
    });

    it("playing a different source replaces which one is tracked as playing", () => {
        const { result } = renderHook(() => useAudioPreview());

        act(() => {
            result.current.play(samplePreview("sample-preview-b", null));
        });
        act(() => {
            result.current.play({
                key: "/api/morph/audio?first=b&second=c&weight=0.5",
                url: "/morph",
                playbackRateHz: null,
            });
        });

        expect(result.current.playingKey).toBe("/api/morph/audio?first=b&second=c&weight=0.5");
    });

    it("two hook instances observe the same playing source", () => {
        const first = renderHook(() => useAudioPreview());
        const second = renderHook(() => useAudioPreview());

        act(() => {
            first.result.current.play(samplePreview("sample-preview-d", null));
        });

        expect(second.result.current.playingKey).toBe("sample-preview-d");
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
                // A real media element resets its rate to the default on a new source: the order under test.
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
        /** Hands every `new Audio()` in the module under test this one recording element. */
        function audioConstructorStub(): RecordingAudio {
            return element;
        }

        vi.stubGlobal("Audio", audioConstructorStub);
        vi.resetModules();
        const { useAudioPreview: freshUseAudioPreview, samplePreview: freshSamplePreview } =
            await import("../../src/samples/useAudioPreview");
        const { result } = renderHook(() => freshUseAudioPreview());

        act(() => {
            result.current.play(freshSamplePreview("sample-preview-e", 8363));
        });

        expect(writes).toEqual(["src", "playbackRate"]);
        expect(element.playbackRate).toBeCloseTo(8363 / NOMINAL_WAV_RATE_HZ);
        vi.unstubAllGlobals();
    });
});
