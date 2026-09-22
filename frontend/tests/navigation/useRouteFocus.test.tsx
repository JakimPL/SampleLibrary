import { renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useRouteFocus } from "../../src/navigation/useRouteFocus";
import { useSelectionStore } from "../../src/workspace/selectionStore";

describe("useRouteFocus", () => {
    it("focuses the sample a view names", () => {
        renderHook(() => {
            useRouteFocus({ kind: "sample", sampleHash: "abc" });
        });

        expect(useSelectionStore.getState().focusedSampleHash).toBe("abc");
        expect(useSelectionStore.getState().highlighted).toEqual({ kind: "sample", hash: "abc" });
    });

    it("focuses the module a view names", () => {
        renderHook(() => {
            useRouteFocus({ kind: "module", moduleHash: "def" });
        });

        expect(useSelectionStore.getState().focusedModuleHash).toBe("def");
    });

    it("leaves the selection alone for a panel view", () => {
        useSelectionStore.getState().focusSample("kept");

        renderHook(() => {
            useRouteFocus({ kind: "panel", panelId: "cloud" });
        });

        expect(useSelectionStore.getState().focusedSampleHash).toBe("kept");
    });
});
