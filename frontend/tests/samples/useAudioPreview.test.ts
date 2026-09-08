import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NOMINAL_WAV_RATE_HZ, REFERENCE_NOTE } from "../../src/samples/nominalRate";
import { previewPlaybackRate, useAudioPreview } from "../../src/samples/useAudioPreview";

describe("previewPlaybackRate", () => {
    it("plays the stored file as it stands when no pitch is known", () => {
        expect(previewPlaybackRate(null)).toBe(1);
    });

    it("runs the stored file at the ratio between an occurrence's rate and the file's own", () => {
        const rate = previewPlaybackRate({ rateHz: 8363, soundedNote: REFERENCE_NOTE });

        expect(rate).toBeCloseTo(8363 / NOMINAL_WAV_RATE_HZ);
    });

    it("sounds a note an octave above the reference key twice as fast", () => {
        const rate = previewPlaybackRate({ rateHz: 8363, soundedNote: REFERENCE_NOTE + 12 });

        expect(rate).toBeCloseTo((8363 * 2) / NOMINAL_WAV_RATE_HZ);
    });

    it("sounds a note an octave below the reference key half as fast", () => {
        const rate = previewPlaybackRate({ rateHz: 8363, soundedNote: REFERENCE_NOTE - 12 });

        expect(rate).toBeCloseTo(8363 / 2 / NOMINAL_WAV_RATE_HZ);
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
