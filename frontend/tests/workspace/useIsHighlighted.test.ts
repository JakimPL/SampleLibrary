import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useSelectionStore } from "../../src/workspace/selectionStore";
import { useIsHighlighted } from "../../src/workspace/useIsHighlighted";

describe("useIsHighlighted", () => {
    it("is false when nothing is highlighted", () => {
        const { result } = renderHook(() => useIsHighlighted({ kind: "sample", hash: "sample-a" }));

        expect(result.current).toBe(false);
    });

    it("is true once the same kind and hash are highlighted", () => {
        const { result } = renderHook(() => useIsHighlighted({ kind: "sample", hash: "sample-a" }));

        act(() => {
            useSelectionStore.getState().highlightEntity({ kind: "sample", hash: "sample-a" });
        });

        expect(result.current).toBe(true);
    });

    it("stays false for a different hash of the same kind", () => {
        const { result } = renderHook(() => useIsHighlighted({ kind: "sample", hash: "sample-a" }));

        act(() => {
            useSelectionStore.getState().highlightEntity({ kind: "sample", hash: "sample-b" });
        });

        expect(result.current).toBe(false);
    });

    it("stays false for the same hash of a different kind", () => {
        const { result } = renderHook(() => useIsHighlighted({ kind: "sample", hash: "shared-hash" }));

        act(() => {
            useSelectionStore.getState().highlightEntity({ kind: "module", hash: "shared-hash" });
        });

        expect(result.current).toBe(false);
    });
});
