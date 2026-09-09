import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
