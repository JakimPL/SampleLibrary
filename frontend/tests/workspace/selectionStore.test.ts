import { describe, expect, it } from "vitest";

import { useSelectionStore } from "../../src/workspace/selectionStore";

describe("selectionStore", () => {
    it("starts with nothing highlighted or focused", () => {
        expect(useSelectionStore.getState()).toMatchObject({
            highlighted: null,
            focusedSampleHash: null,
            focusedModuleHash: null,
        });
    });

    it("highlightEntity sets the highlighted entity without touching either focus slot", () => {
        useSelectionStore.getState().highlightEntity({ kind: "sample", hash: "sample-a" });

        const state = useSelectionStore.getState();
        expect(state.highlighted).toEqual({ kind: "sample", hash: "sample-a" });
        expect(state.focusedSampleHash).toBeNull();
        expect(state.focusedModuleHash).toBeNull();
    });

    it("clearHighlight removes the highlight without touching either focus slot", () => {
        useSelectionStore.getState().focusSample("sample-a");

        useSelectionStore.getState().clearHighlight();

        const state = useSelectionStore.getState();
        expect(state.highlighted).toBeNull();
        expect(state.focusedSampleHash).toBe("sample-a");
    });

    it("focusSample sets both the focused sample and the highlight, leaving the focused module untouched", () => {
        useSelectionStore.getState().focusModule("module-a");

        useSelectionStore.getState().focusSample("sample-a");

        const state = useSelectionStore.getState();
        expect(state.focusedSampleHash).toBe("sample-a");
        expect(state.focusedModuleHash).toBe("module-a");
        expect(state.highlighted).toEqual({ kind: "sample", hash: "sample-a" });
    });

    it("focusModule sets both the focused module and the highlight, leaving the focused sample untouched", () => {
        useSelectionStore.getState().focusSample("sample-a");

        useSelectionStore.getState().focusModule("module-a");

        const state = useSelectionStore.getState();
        expect(state.focusedModuleHash).toBe("module-a");
        expect(state.focusedSampleHash).toBe("sample-a");
        expect(state.highlighted).toEqual({ kind: "module", hash: "module-a" });
    });
});
