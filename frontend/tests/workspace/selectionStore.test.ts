import { describe, expect, it } from "vitest";

import { INITIAL_SELECTION_STATE, morphAnchorOf, useSelectionStore } from "../../src/workspace/selectionStore";

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

describe("morphAnchorOf", () => {
    it("takes the highlighted sample, the one in hand", () => {
        useSelectionStore.setState(INITIAL_SELECTION_STATE);
        useSelectionStore.getState().focusSample("sample-a");
        useSelectionStore.getState().highlightEntity({ kind: "sample", hash: "sample-b" });

        expect(morphAnchorOf(useSelectionStore.getState())).toBe("sample-b");
    });

    it("falls back to the focused sample while a module is highlighted", () => {
        useSelectionStore.setState(INITIAL_SELECTION_STATE);
        useSelectionStore.getState().focusSample("sample-a");
        useSelectionStore.getState().highlightEntity({ kind: "module", hash: "module-a" });

        expect(morphAnchorOf(useSelectionStore.getState())).toBe("sample-a");
    });

    it("answers with nothing while no sample is in hand", () => {
        useSelectionStore.setState(INITIAL_SELECTION_STATE);
        useSelectionStore.getState().highlightEntity({ kind: "module", hash: "module-a" });

        expect(morphAnchorOf(useSelectionStore.getState())).toBeNull();
    });
});
