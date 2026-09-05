import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useAudioPreview } from "../../src/samples/useAudioPreview";

describe("useAudioPreview", () => {
    it("tracks the most recently played sample as playing", () => {
        const { result } = renderHook(() => useAudioPreview());

        act(() => {
            result.current.play("sample-preview-a");
        });

        expect(result.current.playingHash).toBe("sample-preview-a");
    });

    it("playing a different sample replaces which one is tracked as playing", () => {
        const { result } = renderHook(() => useAudioPreview());

        act(() => {
            result.current.play("sample-preview-b");
        });
        act(() => {
            result.current.play("sample-preview-c");
        });

        expect(result.current.playingHash).toBe("sample-preview-c");
    });

    it("two hook instances observe the same playing sample", () => {
        const first = renderHook(() => useAudioPreview());
        const second = renderHook(() => useAudioPreview());

        act(() => {
            first.result.current.play("sample-preview-d");
        });

        expect(second.result.current.playingHash).toBe("sample-preview-d");
    });
});
